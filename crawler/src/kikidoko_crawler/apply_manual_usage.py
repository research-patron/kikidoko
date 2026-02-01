from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Iterable

from .firestore_client import get_client


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply manual usage summaries to equipment documents."
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
        "--input",
        default="crawler/manual_usage_overrides.json",
        help="Path to manual usage JSON file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print updates without writing to Firestore.",
    )
    return parser.parse_args(list(argv))


def load_overrides(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError("Overrides JSON must be a list.")
    return data


def main() -> None:
    args = parse_args(sys.argv[1:])
    if not args.project_id:
        print("Missing --project-id or KIKIDOKO_PROJECT_ID.", file=sys.stderr)
        sys.exit(2)
    overrides = load_overrides(args.input)

    client = get_client(args.project_id, args.credentials or None)
    collection = client.collection("equipment")
    updated_at = datetime.now(timezone.utc).isoformat()

    for entry in overrides:
        doc_id = entry.get("doc_id")
        if not doc_id:
            print("Skipped entry without doc_id.", file=sys.stderr)
            continue
        summary = entry.get("summary", "")
        bullets = entry.get("bullets", [])
        sources = entry.get("source_titles", [])
        dois = entry.get("source_dois", [])
        update = {
            "usage_manual_summary": summary,
            "usage_manual_bullets": bullets,
            "usage_manual_sources": sources,
            "usage_manual_dois": dois,
            "usage_manual_editor": "manual",
            "usage_manual_updated_at": updated_at,
        }
        if args.dry_run:
            print(f"[dry-run] {doc_id}: {summary}")
            continue
        collection.document(doc_id).set(update, merge=True)
        print(f"Updated {doc_id}")


if __name__ == "__main__":
    main()
