from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Tuple

from .firestore_client import get_client
from .utils import build_search_aliases, build_search_tokens, guess_prefecture, resolve_region


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill search_tokens (and optionally region) in Firestore."
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
        "--dry-run",
        action="store_true",
        help="Only report changes without writing to Firestore.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Stop after processing this many documents (0 = no limit).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=400,
        help="Number of updates per batch commit (max 500).",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="Seconds to sleep after each batch commit.",
    )
    parser.add_argument(
        "--force-tokens",
        action="store_true",
        help="Recompute search_tokens even if already present.",
    )
    parser.add_argument(
        "--force-aliases",
        action="store_true",
        help="Recompute search_aliases even if already present.",
    )
    parser.add_argument(
        "--skip-region",
        action="store_true",
        help="Do not backfill region even if missing.",
    )
    parser.add_argument(
        "--write-summary",
        action="store_true",
        help="Write prefecture summary to stats collection.",
    )
    parser.add_argument(
        "--summary-doc",
        default="prefecture_summary",
        help="Stats document id (default: prefecture_summary).",
    )
    return parser.parse_args(list(argv))


def is_missing(value: Any, expect_list: bool = False) -> bool:
    if value is None:
        return True
    if expect_list and not isinstance(value, list):
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, list) and len(value) == 0:
        return True
    return False


def build_updates(
    data: Dict[str, Any],
    force_tokens: bool,
    force_aliases: bool,
    include_region: bool,
) -> Dict[str, Any]:
    updates: Dict[str, Any] = {}

    name = data.get("name", "")
    org_name = data.get("org_name", "")
    category_general = data.get("category_general", "")
    category_detail = data.get("category_detail", "")
    prefecture = data.get("prefecture", "")
    if not prefecture:
        prefecture = guess_prefecture(data.get("address_raw", "") or org_name)

    current_tokens = data.get("search_tokens")
    if force_tokens or is_missing(current_tokens, expect_list=True):
        tokens = build_search_tokens(
            name, org_name, category_general, category_detail, prefecture
        )
        if tokens:
            updates["search_tokens"] = tokens

    current_aliases = data.get("search_aliases")
    aliases = build_search_aliases(name, org_name, category_general, category_detail)
    current_list = current_aliases if isinstance(current_aliases, list) else []
    if force_aliases or is_missing(current_aliases, expect_list=True) or current_list != aliases:
        updates["search_aliases"] = aliases

    if include_region and is_missing(data.get("region")):
        region = resolve_region(prefecture)
        if region:
            updates["region"] = region

    return updates


def commit_batch(batch, pending: int, sleep_seconds: float) -> None:
    if pending <= 0:
        return
    batch.commit()
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)


def run_backfill(args: argparse.Namespace) -> int:
    if not args.project_id:
        print("Missing --project-id or KIKIDOKO_PROJECT_ID.", file=sys.stderr)
        return 2
    if args.batch_size <= 0 or args.batch_size > 500:
        print("batch-size must be between 1 and 500.", file=sys.stderr)
        return 2
    if args.sleep < 0:
        print("sleep must be 0 or greater.", file=sys.stderr)
        return 2

    client = get_client(args.project_id, args.credentials or None)
    collection = client.collection("equipment")

    total = 0
    updated = 0
    skipped = 0
    errors = 0
    pending = 0
    batch = client.batch()
    prefecture_counts: Dict[str, int] = {}
    prefecture_orgs: Dict[str, set[str]] = {}

    for doc in collection.stream():
        total += 1
        try:
            data = doc.to_dict() or {}
            updates = build_updates(
                data,
                force_tokens=args.force_tokens,
                force_aliases=args.force_aliases,
                include_region=not args.skip_region,
            )
            if args.write_summary:
                org_name = data.get("org_name", "")
                prefecture = data.get("prefecture", "")
                if not prefecture:
                    prefecture = guess_prefecture(data.get("address_raw", "") or org_name)
                if prefecture:
                    prefecture_counts[prefecture] = prefecture_counts.get(prefecture, 0) + 1
                    if org_name:
                        prefecture_orgs.setdefault(prefecture, set()).add(org_name)
        except Exception as exc:  # pragma: no cover - defensive
            errors += 1
            print(f"Failed to process {doc.id}: {exc}", file=sys.stderr)
            continue
        if updates:
            updated += 1
            if not args.dry_run:
                batch.update(doc.reference, updates)
                pending += 1
                if pending >= args.batch_size:
                    commit_batch(batch, pending, args.sleep)
                    batch = client.batch()
                    pending = 0
        else:
            skipped += 1

        if args.limit and total >= args.limit:
            break
        if total % 500 == 0:
            print(f"Processed {total} docs (updated {updated}).")

    if not args.dry_run and pending:
        commit_batch(batch, pending, args.sleep)

    if args.write_summary:
        facility_counts = {
            prefecture: len(orgs) for prefecture, orgs in prefecture_orgs.items()
        }
        top_prefectures = (
            sorted(
                [
                    {
                        "prefecture": prefecture,
                        "equipmentCount": count,
                        "facilityCount": facility_counts.get(prefecture, 0),
                    }
                    for prefecture, count in prefecture_counts.items()
                ],
                key=lambda item: item["equipmentCount"],
                reverse=True,
            )[:6]
        )
        summary_data = {
            "top_prefectures": top_prefectures,
            "prefecture_counts": prefecture_counts,
            "facility_counts": facility_counts,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if args.dry_run:
            print(f"Summary preview: {top_prefectures}")
        else:
            client.collection("stats").document(args.summary_doc).set(summary_data)

    print(
        f"Done. processed={total} updated={updated} skipped={skipped} errors={errors}"
    )
    return 0


def main() -> None:
    args = parse_args(sys.argv[1:])
    sys.exit(run_backfill(args))


if __name__ == "__main__":
    main()
