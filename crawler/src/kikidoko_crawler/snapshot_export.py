from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .firestore_client import get_client

SNAPSHOT_SCHEMA_VERSION = "2"
SNAPSHOT_SORTED_BY = "name_ja_asc"
MAX_TEXT_LEN = 2000
MAX_ABSTRACT_LEN = 1200
MAX_LIST_ITEMS = 12

STRING_FIELDS = (
    "name",
    "category_general",
    "category_detail",
    "org_name",
    "org_type",
    "prefecture",
    "region",
    "external_use",
    "fee_band",
    "source_url",
    "eqnet_url",
    "eqnet_equipment_id",
    "eqnet_match_status",
    "crawled_at",
    "papers_status",
    "papers_updated_at",
    "papers_error",
    "usage_manual_summary",
)
LIST_STRING_FIELDS = (
    "search_aliases",
    "usage_themes",
    "usage_genres",
    "usage_manual_bullets",
)
PAPER_META_FIELDS = (
    "doi",
    "title",
    "url",
    "source",
    "year",
    "genre",
    "genre_ja",
)
PAPER_ABSTRACT_FIELDS = ("abstract_ja", "abstract")


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export Firestore equipment documents as a static gzip snapshot."
    )
    parser.add_argument(
        "--project-id",
        default=os.getenv("KIKIDOKO_PROJECT_ID", ""),
        help="Firestore project id (or set KIKIDOKO_PROJECT_ID).",
    )
    parser.add_argument(
        "--credentials",
        default=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
        help="Service account JSON path (or set GOOGLE_APPLICATION_CREDENTIALS).",
    )
    parser.add_argument(
        "--output",
        default="frontend/public/equipment_snapshot.json.gz",
        help="Output gzip JSON path (default: frontend/public/equipment_snapshot.json.gz).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Stop after this many documents (0 = all).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only count documents and skip file write.",
    )
    return parser.parse_args(list(argv))


def normalize_text(value: Any, max_len: int = MAX_TEXT_LEN) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if max_len > 0 and len(text) > max_len:
        return text[:max_len].rstrip()
    return text


def normalize_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric != numeric:  # NaN
        return None
    return numeric


def normalize_string_list(value: Any, max_items: int = MAX_LIST_ITEMS) -> list[str]:
    if not isinstance(value, list):
        return []
    results: list[str] = []
    seen = set()
    for entry in value:
        text = normalize_text(entry, 160)
        if not text or text in seen:
            continue
        seen.add(text)
        results.append(text)
        if len(results) >= max_items:
            break
    return results


def normalize_papers(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for paper in value:
        if not isinstance(paper, dict):
            continue
        compact: dict[str, Any] = {}
        for field in PAPER_META_FIELDS:
            raw = paper.get(field)
            if raw is None:
                continue
            if field == "year":
                if isinstance(raw, (int, float)):
                    year = int(raw)
                    if year > 0:
                        compact[field] = year
                else:
                    year_text = normalize_text(raw, 8)
                    if year_text:
                        compact[field] = year_text
                continue
            text = normalize_text(raw, 512)
            if text:
                compact[field] = text
        for field in PAPER_ABSTRACT_FIELDS:
            abstract = normalize_text(paper.get(field), MAX_ABSTRACT_LEN)
            if abstract:
                compact[field] = abstract
        if compact:
            normalized.append(compact)
    return normalized


def compact_equipment_document(data: dict[str, Any], snapshot_id: str) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    equipment_id = normalize_text(data.get("equipment_id"), 160) or snapshot_id
    doc_id = normalize_text(data.get("doc_id"), 160) or snapshot_id
    compact["equipment_id"] = equipment_id
    compact["doc_id"] = doc_id

    for field in STRING_FIELDS:
        text = normalize_text(data.get(field))
        if text:
            compact[field] = text

    address = normalize_text(data.get("address_raw") or data.get("address"))
    if address:
        compact["address_raw"] = address

    lat = normalize_float(data.get("lat"))
    lng = normalize_float(data.get("lng"))
    if lat is not None:
        compact["lat"] = lat
    if lng is not None:
        compact["lng"] = lng

    for field in LIST_STRING_FIELDS:
        values = normalize_string_list(data.get(field))
        if values:
            compact[field] = values

    papers = normalize_papers(data.get("papers"))
    if papers:
        compact["papers"] = papers

    return compact


def snapshot_sort_key(item: dict[str, Any]) -> tuple[str, str]:
    name = normalize_text(item.get("name"), 512)
    item_id = normalize_text(item.get("equipment_id") or item.get("doc_id"), 256)
    return (name, item_id)


def run_export(args: argparse.Namespace) -> int:
    if not args.project_id:
        print("Missing --project-id or KIKIDOKO_PROJECT_ID.", file=sys.stderr)
        return 2

    client = get_client(args.project_id, args.credentials or None)
    collection = client.collection("equipment")

    items: list[dict[str, Any]] = []
    for index, snapshot in enumerate(collection.stream(), start=1):
        data = snapshot.to_dict() or {}
        items.append(compact_equipment_document(data, snapshot.id))
        if args.limit and index >= args.limit:
            break
        if index % 1000 == 0:
            print(f"Collected {index} equipment docs...")

    items.sort(key=snapshot_sort_key)
    generated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "sorted_by": SNAPSHOT_SORTED_BY,
        "generated_at": generated_at,
        "project_id": args.project_id,
        "count": len(items),
        "items": items,
    }

    if args.dry_run:
        print(
            "Snapshot dry-run: "
            f"schema={SNAPSHOT_SCHEMA_VERSION} sorted_by={SNAPSHOT_SORTED_BY} "
            f"count={payload['count']} generated_at={generated_at} output={args.output}"
        )
        return 0

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(output_path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))

    print(f"Snapshot exported: {output_path} (count={payload['count']})")
    return 0


def main() -> None:
    args = parse_args(sys.argv[1:])
    raise SystemExit(run_export(args))


if __name__ == "__main__":
    main()
