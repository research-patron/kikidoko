from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .config import load_settings
from .firestore_client import get_client, upsert_equipment
from .models import EquipmentRecord
from .normalizer import normalize_equipment


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kikidoko crawler")
    parser.add_argument(
        "--source",
        required=True,
        choices=["university", "csv"],
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

    raise SystemExit(f"Source {args.source} is not implemented yet")

    records: list[EquipmentRecord] = [normalize_equipment(raw) for raw in []]

    if dry_run:
        _emit_records(records, output_path)
        logger.info("Dry run complete: %s records", len(records))
        return 0

    client = get_client(settings.project_id, settings.credentials_path)
    created = 0
    updated = 0
    for record in records:
        _, status = upsert_equipment(client, record)
        if status == "created":
            created += 1
        else:
            updated += 1
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


if __name__ == "__main__":
    raise SystemExit(main())
