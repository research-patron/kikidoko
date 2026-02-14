from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from google.api_core import exceptions as gcloud_exceptions

from .firestore_client import get_client
from .models import RawEquipment
from .normalizer import normalize_equipment
from .sources import available_sources, fetch_records
from .sources.table_sources import fetch_table_source
from .sources.table_utils import TableConfig, fetch_table_records

DEFAULT_REGISTRY_PATH = "crawler/config/source_registry_low_count.json"
DEFAULT_PREVIEW_OUT = "crawler/source_registry_sync_preview.csv"
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
PREVIEW_FIELDNAMES = [
    "registry_key",
    "org_name",
    "prefecture",
    "parser_type",
    "source_handler",
    "url",
    "fetched_raw_count",
    "normalized_count",
    "fetch_status",
    "action_hint",
    "diagnosis",
    "would_create",
    "would_update",
]


@dataclass(frozen=True)
class RegistryEntry:
    key: str
    org_name: str
    prefecture: str
    url: str
    parser_type: str
    source_handler: str
    category_hint: str
    external_use: str
    selectors: dict[str, Any]
    enabled: bool


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync equipment records from low-count source registry into Firestore."
    )
    parser.add_argument(
        "--project-id",
        default=os.getenv("KIKIDOKO_PROJECT_ID", ""),
        help="Firestore project id (or KIKIDOKO_PROJECT_ID).",
    )
    parser.add_argument(
        "--credentials",
        default=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
        help="Service account path (or GOOGLE_APPLICATION_CREDENTIALS).",
    )
    parser.add_argument(
        "--registry",
        default=DEFAULT_REGISTRY_PATH,
        help=f"Registry JSON path (default: {DEFAULT_REGISTRY_PATH}).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=25,
        help="Request timeout seconds.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Firestore batch write size (1-500).",
    )
    parser.add_argument(
        "--limit-orgs",
        type=int,
        default=0,
        help="Process first N registry organizations (0=all).",
    )
    parser.add_argument(
        "--limit-records-per-org",
        type=int,
        default=0,
        help="Limit fetched records per organization (0=all).",
    )
    parser.add_argument(
        "--priority-csv",
        default="",
        help="Optional low_count_org_priority.csv path to filter organizations.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write Firestore.",
    )
    parser.add_argument(
        "--preview-out",
        default=DEFAULT_PREVIEW_OUT,
        help=f"Preview CSV path (default: {DEFAULT_PREVIEW_OUT}).",
    )
    parser.add_argument(
        "--registry-version",
        default="",
        help="Override registry version marker written to Firestore.",
    )
    return parser.parse_args(list(argv))


def clean_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(text.split()).strip()


def resolve_workspace_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    if path.exists():
        return path
    return WORKSPACE_ROOT / path


def parse_registry(path: Path) -> tuple[str, list[RegistryEntry]]:
    if not path.exists():
        raise FileNotFoundError(f"Registry file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        version = clean_text(payload.get("version", ""))
        entries_raw = payload.get("entries")
    else:
        version = ""
        entries_raw = payload
    if not isinstance(entries_raw, list):
        raise ValueError("Registry entries must be a list.")

    entries: list[RegistryEntry] = []
    for item in entries_raw:
        if not isinstance(item, dict):
            continue
        key = clean_text(item.get("key", ""))
        org_name = clean_text(item.get("org_name", ""))
        if not key or not org_name:
            continue
        selectors = item.get("selectors") if isinstance(item.get("selectors"), dict) else {}
        entries.append(
            RegistryEntry(
                key=key,
                org_name=org_name,
                prefecture=clean_text(item.get("prefecture", "")),
                url=clean_text(item.get("url", "")),
                parser_type=clean_text(item.get("parser_type", "table_utils")) or "table_utils",
                source_handler=clean_text(item.get("source_handler", "")),
                category_hint=clean_text(item.get("category_hint", "")),
                external_use=clean_text(item.get("external_use", "")),
                selectors=selectors,
                enabled=bool(item.get("enabled", True)),
            )
        )
    return version, entries


def load_priority_orgs(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"Priority CSV not found: {path}")
    names: set[str] = set()
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            org_name = clean_text(row.get("org_name", ""))
            if org_name:
                names.add(org_name)
    return names


def build_table_config(entry: RegistryEntry) -> TableConfig:
    selectors = entry.selectors or {}
    link_patterns = selectors.get("link_patterns", [])
    required_table_links = selectors.get("required_table_links", [])
    return TableConfig(
        key=entry.key,
        org_name=entry.org_name,
        url=entry.url,
        org_type=clean_text(selectors.get("org_type", "")),
        category_hint=entry.category_hint,
        external_use=entry.external_use,
        link_patterns=tuple(link_patterns if isinstance(link_patterns, list) else []),
        required_table_links=tuple(
            required_table_links if isinstance(required_table_links, list) else []
        ),
        force_apparent_encoding=bool(selectors.get("force_apparent_encoding", False)),
    )


def fetch_raw_records_for_entry(
    entry: RegistryEntry,
    timeout: int,
    limit_records: int,
) -> tuple[list[RawEquipment], str]:
    parser_type = entry.parser_type
    if parser_type == "query_only":
        return [], "query_only"

    try:
        if parser_type == "source_handler":
            source_key = entry.source_handler or entry.key
            if source_key not in available_sources():
                return [], f"unknown_source_handler:{source_key}"
            rows = fetch_records(source=source_key, timeout=timeout, limit=limit_records)
            return rows, "ok"

        if parser_type in {"table_utils", "table"}:
            if not entry.url:
                return [], "missing_url"
            config = build_table_config(entry)
            rows = fetch_table_records(config=config, timeout=timeout, limit=limit_records)
            return rows, "ok"

        if parser_type == "table_source":
            rows = fetch_table_source(source_key=entry.key, timeout=timeout, limit=limit_records)
            return rows, "ok"

        return [], f"unsupported_parser:{parser_type}"
    except Exception as exc:  # pragma: no cover
        return [], f"error:{exc}"


def hydrate_raw(raw: RawEquipment, entry: RegistryEntry) -> RawEquipment:
    return RawEquipment(
        equipment_id=raw.equipment_id,
        name=raw.name,
        category=raw.category,
        category_general=raw.category_general,
        category_detail=raw.category_detail,
        org_name=raw.org_name or entry.org_name,
        org_type=raw.org_type,
        prefecture=raw.prefecture or entry.prefecture,
        address_raw=raw.address_raw or entry.org_name,
        lat=raw.lat,
        lng=raw.lng,
        external_use=raw.external_use or entry.external_use,
        fee_note=raw.fee_note,
        conditions_note=raw.conditions_note,
        source_url=raw.source_url or entry.url,
        source_updated_at=raw.source_updated_at,
    )


def build_existing_index(client, org_names: list[str]) -> tuple[dict[str, Any], bool]:
    index: dict[str, Any] = {"equipment_id": {}, "dedupe_key": {}}
    collection = client.collection("equipment")

    for org_name in sorted(set(org_names)):
        success = False
        for attempt in range(3):
            try:
                query = collection.where("org_name", "==", org_name)
                for doc in query.stream(timeout=60, retry=None):
                    data = doc.to_dict() or {}
                    equipment_id = clean_text(data.get("equipment_id", ""))
                    dedupe_key = clean_text(data.get("dedupe_key", ""))
                    if equipment_id:
                        index["equipment_id"][equipment_id] = doc.reference
                    if dedupe_key:
                        index["dedupe_key"][dedupe_key] = doc.reference
                success = True
                break
            except (gcloud_exceptions.ResourceExhausted, gcloud_exceptions.RetryError):
                wait = min(60, 10 * (attempt + 1))
                time.sleep(wait)
            except (
                gcloud_exceptions.ServiceUnavailable,
                gcloud_exceptions.GoogleAPICallError,
            ):
                wait = min(60, 10 * (attempt + 1))
                time.sleep(wait)
        if not success:
            return index, False

    return index, True


def safe_doc_id(value: str) -> str:
    return value.replace("/", "_")


def classify_preview(fetch_status: str, normalized_count: int) -> tuple[str, str]:
    if fetch_status == "query_only":
        return ("implement_source", "公式URLと取得方式(parser_type)の設定が未完了")
    if fetch_status == "ok" and normalized_count > 0:
        return ("sync_now", "取得成功")
    if fetch_status == "ok":
        return ("verify_url", "取得0件（URL/selectorの要再確認）")
    if fetch_status.startswith("error:"):
        return ("verify_url", fetch_status[6:])
    return ("verify_url", fetch_status or "unknown")


def commit_batch_with_retry(batch, retries: int = 4) -> None:
    for attempt in range(retries):
        try:
            batch.commit()
            return
        except (
            gcloud_exceptions.ResourceExhausted,
            gcloud_exceptions.RetryError,
            gcloud_exceptions.ServiceUnavailable,
        ):
            if attempt + 1 >= retries:
                raise
            time.sleep(min(120, 10 * (attempt + 1)))


def run(args: argparse.Namespace) -> int:
    if args.batch_size <= 0 or args.batch_size > 500:
        print("batch-size must be between 1 and 500.", file=sys.stderr)
        return 2

    registry_version, entries = parse_registry(resolve_workspace_path(args.registry))
    if args.registry_version:
        registry_version = clean_text(args.registry_version)
    if not registry_version:
        registry_version = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    entries = [entry for entry in entries if entry.enabled]
    if args.priority_csv:
        target_orgs = load_priority_orgs(resolve_workspace_path(args.priority_csv))
        entries = [entry for entry in entries if entry.org_name in target_orgs]

    if args.limit_orgs > 0:
        entries = entries[: args.limit_orgs]

    preview_rows: list[dict[str, Any]] = []
    normalized_records: list[tuple[RegistryEntry, Any]] = []

    for entry in entries:
        raw_rows, fetch_status = fetch_raw_records_for_entry(
            entry=entry,
            timeout=args.timeout,
            limit_records=args.limit_records_per_org,
        )
        record_count = 0
        for raw in raw_rows:
            hydrated = hydrate_raw(raw, entry)
            normalized = normalize_equipment(hydrated)
            normalized_records.append((entry, normalized))
            record_count += 1
        action_hint, diagnosis = classify_preview(fetch_status, record_count)
        preview_rows.append(
            {
                "registry_key": entry.key,
                "org_name": entry.org_name,
                "prefecture": entry.prefecture,
                "parser_type": entry.parser_type,
                "source_handler": entry.source_handler,
                "url": entry.url,
                "fetched_raw_count": len(raw_rows),
                "normalized_count": record_count,
                "fetch_status": fetch_status,
                "action_hint": action_hint,
                "diagnosis": diagnosis,
                "would_create": "",
                "would_update": "",
            }
        )

    if not normalized_records:
        preview_out = resolve_workspace_path(args.preview_out)
        preview_out.parent.mkdir(parents=True, exist_ok=True)
        with preview_out.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=PREVIEW_FIELDNAMES,
            )
            writer.writeheader()
            for row in preview_rows:
                writer.writerow(row)
        print(f"No normalized records. Preview written: {preview_out}")
        return 0

    if not args.project_id:
        if args.dry_run:
            preview_out = resolve_workspace_path(args.preview_out)
            preview_out.parent.mkdir(parents=True, exist_ok=True)
            with preview_out.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=PREVIEW_FIELDNAMES,
                )
                writer.writeheader()
                for row in preview_rows:
                    writer.writerow(row)
            print("Dry-run without Firestore project id: create/update classification skipped.")
            print(f"Preview written: {preview_out}")
            return 0
        print("Missing --project-id or KIKIDOKO_PROJECT_ID.", file=sys.stderr)
        return 2

    client = get_client(args.project_id, args.credentials or None)
    org_names = [record.org_name for _, record in normalized_records if record.org_name]
    index, index_ready = build_existing_index(client=client, org_names=org_names)
    collection = client.collection("equipment")

    now_iso = datetime.now(timezone.utc).isoformat()
    created = 0
    updated = 0
    by_org_create: Counter[str] = Counter()
    by_org_update: Counter[str] = Counter()

    entry_would_create: Counter[str] = Counter()
    entry_would_update: Counter[str] = Counter()

    batch = client.batch()
    pending = 0

    for entry, record in normalized_records:
        data = record.to_firestore()
        data.update(
            {
                "source_site": entry.key,
                "source_registry_url": entry.url,
                "source_registry_synced_at": now_iso,
                "source_registry_version": registry_version,
            }
        )

        ref = None
        if index_ready:
            if record.equipment_id:
                ref = index["equipment_id"].get(record.equipment_id)
            if not ref and record.dedupe_key:
                ref = index["dedupe_key"].get(record.dedupe_key)

        is_update = bool(ref)
        if not ref:
            if index_ready:
                ref = collection.document()
            else:
                if record.equipment_id:
                    ref = collection.document(safe_doc_id(record.equipment_id))
                else:
                    ref = collection.document()

        if not record.equipment_id:
            data["equipment_id"] = ref.id

        if is_update:
            entry_would_update[entry.key] += 1
            by_org_update[entry.org_name] += 1
            updated += 1
        else:
            entry_would_create[entry.key] += 1
            by_org_create[entry.org_name] += 1
            created += 1

        if not args.dry_run:
            batch.set(ref, data, merge=True)
            pending += 1
            if pending >= args.batch_size:
                commit_batch_with_retry(batch)
                batch = client.batch()
                pending = 0

        equipment_id = clean_text(data.get("equipment_id", ""))
        if equipment_id:
            index["equipment_id"][equipment_id] = ref
        if record.dedupe_key:
            index["dedupe_key"][record.dedupe_key] = ref

    if not args.dry_run and pending:
        commit_batch_with_retry(batch)

    for row in preview_rows:
        key = row["registry_key"]
        row["would_create"] = str(int(entry_would_create.get(key, 0)))
        row["would_update"] = str(int(entry_would_update.get(key, 0)))

    preview_out = resolve_workspace_path(args.preview_out)
    preview_out.parent.mkdir(parents=True, exist_ok=True)
    with preview_out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=PREVIEW_FIELDNAMES,
        )
        writer.writeheader()
        for row in preview_rows:
            writer.writerow(row)

    print(
        "Done. "
        f"records={len(normalized_records)} "
        f"created={created} "
        f"updated={updated} "
        f"dry_run={args.dry_run}"
    )
    print(f"Preview CSV: {preview_out}")
    return 0


def main() -> None:
    args = parse_args(sys.argv[1:])
    sys.exit(run(args))


if __name__ == "__main__":
    main()
