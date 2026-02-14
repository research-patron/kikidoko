from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .firestore_client import get_client


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


def run_export(args: argparse.Namespace) -> int:
    if not args.project_id:
        print("Missing --project-id or KIKIDOKO_PROJECT_ID.", file=sys.stderr)
        return 2

    client = get_client(args.project_id, args.credentials or None)
    collection = client.collection("equipment")

    items: list[dict] = []
    for index, snapshot in enumerate(collection.stream(), start=1):
        data = snapshot.to_dict() or {}
        if not data.get("equipment_id"):
            data["equipment_id"] = snapshot.id
        if not data.get("doc_id"):
            data["doc_id"] = snapshot.id
        items.append(data)
        if args.limit and index >= args.limit:
            break
        if index % 1000 == 0:
            print(f"Collected {index} equipment docs...")

    generated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "generated_at": generated_at,
        "project_id": args.project_id,
        "count": len(items),
        "items": items,
    }

    if args.dry_run:
        print(
            f"Snapshot dry-run: count={payload['count']} generated_at={generated_at} output={args.output}"
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
