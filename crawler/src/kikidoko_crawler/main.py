from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

from google.api_core import exceptions as gcloud_exceptions

from .config import load_settings
from .firestore_client import get_client
from .models import EquipmentRecord
from .normalizer import normalize_equipment
from .sources import available_sources, fetch_records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kikidoko crawler")
    parser.add_argument(
        "--source",
        required=True,
        choices=available_sources(),
        help="Data source to crawl",
    )
    parser.add_argument("--dry-run", action="store_true", help="Skip Firestore writes")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of items to process (0 = no limit)",
    )
    parser.add_argument("--output", help="Write normalized records to a JSONL file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = load_settings()
    dry_run = settings.dry_run or args.dry_run
    output_path = args.output or settings.output_path

    logging.basicConfig(level=settings.log_level, format="%(levelname)s: %(message)s")
    logger = logging.getLogger(__name__)

    if not dry_run and not settings.project_id:
        raise SystemExit("KIKIDOKO_PROJECT_ID is required when not running dry")

    logger.info(
        "Starting crawl: source=%s dry_run=%s limit=%s output=%s",
        args.source,
        dry_run,
        args.limit or "none",
        output_path or "stdout",
    )

    raw_records = fetch_records(args.source, settings.request_timeout, args.limit)
    records: list[EquipmentRecord] = [normalize_equipment(raw) for raw in raw_records]

    if dry_run:
        _emit_records(records, output_path)
        logger.info("Dry run complete: %s records", len(records))
        return 0

    client = get_client(settings.project_id, settings.credentials_path)
    index, index_ready = _build_existing_index(logger, client, records)
    created = 0
    updated = 0
    for record in records:
        status = _upsert_with_retry(logger, client, record, index, index_ready)
        if status == "created":
            created += 1
        else:
            updated += 1
        time.sleep(0.5)
    logger.info("Upsert complete: created=%s updated=%s", created, updated)
    return 0


def _emit_records(records: list[EquipmentRecord], output_path: str | None) -> None:
    lines = [json.dumps(record.to_firestore(), ensure_ascii=False) for record in records]
    if output_path:
        path = Path(output_path)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return
    for line in lines:
        print(line)


def _upsert_with_retry(
    logger: logging.Logger,
    client,
    record: EquipmentRecord,
    index: dict,
    index_ready: bool,
    retries: int = 3,
) -> str:
    for attempt in range(retries):
        try:
            status = _upsert_with_index(client, record, index, index_ready)
            return status
        except (gcloud_exceptions.ResourceExhausted, gcloud_exceptions.RetryError) as exc:
            wait = min(60, 5 * (attempt + 1))
            logger.warning(
                "Firestore quota exceeded. Retrying in %ss (%s/%s): %s",
                wait,
                attempt + 1,
                retries,
                exc,
            )
            time.sleep(wait)
    return _upsert_with_index(client, record, index, index_ready)


def _build_existing_index(
    logger: logging.Logger, client, records: list[EquipmentRecord]
) -> tuple[dict[str, dict[str, object]], bool]:
    index: dict[str, dict[str, object]] = {"equipment_id": {}, "dedupe_key": {}}
    org_names = sorted({record.org_name for record in records if record.org_name})
    collection = client.collection("equipment")
    for org_name in org_names:
        success = False
        for attempt in range(3):
            try:
                query = collection.where("org_name", "==", org_name)
                for doc in query.stream(timeout=60, retry=None):
                    data = doc.to_dict() or {}
                    equipment_id = data.get("equipment_id")
                    dedupe_key = data.get("dedupe_key")
                    if equipment_id:
                        index["equipment_id"][equipment_id] = doc.reference
                    if dedupe_key:
                        index["dedupe_key"][dedupe_key] = doc.reference
                success = True
                break
            except (gcloud_exceptions.ResourceExhausted, gcloud_exceptions.RetryError) as exc:
                wait = min(60, 10 * (attempt + 1))
                logger.warning(
                    "Firestore quota exceeded while building index. Retrying in %ss (%s/3): %s",
                    wait,
                    attempt + 1,
                    exc,
                )
                time.sleep(wait)
        if not success:
            logger.warning(
                "Firestore index build failed due to quota. Proceeding without read checks."
            )
            return index, False
    return index, True


def _upsert_with_index(
    client, record: EquipmentRecord, index: dict[str, dict[str, object]], index_ready: bool
) -> str:
    data = record.to_firestore()
    collection = client.collection("equipment")
    if not index_ready:
        doc_id = _safe_doc_id(record.equipment_id or record.dedupe_key or "")
        doc_ref = collection.document(doc_id) if doc_id else collection.document()
        if not record.equipment_id and doc_id == "":
            data["equipment_id"] = doc_ref.id
        doc_ref.set(data, merge=True)
        if data.get("equipment_id"):
            index["equipment_id"][data["equipment_id"]] = doc_ref
        if record.dedupe_key:
            index["dedupe_key"][record.dedupe_key] = doc_ref
        return "created"

    ref = None
    if record.equipment_id:
        ref = index["equipment_id"].get(record.equipment_id)
    if not ref and record.dedupe_key:
        ref = index["dedupe_key"].get(record.dedupe_key)
    if ref:
        ref.set(data, merge=True)
        return "updated"

    doc_ref = collection.document()
    if not record.equipment_id:
        data["equipment_id"] = doc_ref.id
    doc_ref.set(data)
    if data.get("equipment_id"):
        index["equipment_id"][data["equipment_id"]] = doc_ref
    if record.dedupe_key:
        index["dedupe_key"][record.dedupe_key] = doc_ref
    return "created"


def _safe_doc_id(value: str) -> str:
    return value.replace("/", "_")


if __name__ == "__main__":
    raise SystemExit(main())
