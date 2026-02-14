from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from google.api_core import exceptions as gcloud_exceptions

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
    parser.add_argument(
        "--write-ui-filters",
        action="store_true",
        help="Write UI filter document to stats collection.",
    )
    parser.add_argument(
        "--ui-filters-doc",
        default="ui_filters",
        help="Stats document id for UI filters (default: ui_filters).",
    )
    parser.add_argument(
        "--write-prefecture-orgs",
        action="store_true",
        help="Write prefecture org list docs under stats/prefecture_orgs.",
    )
    parser.add_argument(
        "--prefecture-orgs-doc",
        default="prefecture_orgs",
        help="Stats document id for prefecture org parent (default: prefecture_orgs).",
    )
    parser.add_argument(
        "--prefecture-orgs-subcollection",
        default="prefectures",
        help="Subcollection name for prefecture org docs (default: prefectures).",
    )
    parser.add_argument(
        "--write-data-version",
        action="store_true",
        help="Write data version document to stats collection.",
    )
    parser.add_argument(
        "--data-version-doc",
        default="data_version",
        help="Stats document id for data version (default: data_version).",
    )
    parser.add_argument(
        "--read-page-size",
        type=int,
        default=400,
        help="Firestore read page size for backfill scan (default: 400).",
    )
    parser.add_argument(
        "--read-max-retries",
        type=int,
        default=8,
        help="Max retries per read page on transient errors (default: 8).",
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


def sorted_unique(values: Iterable[str]) -> list[str]:
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    return sorted(set(cleaned))


def is_retryable_stream_error(exc: Exception) -> bool:
    if isinstance(
        exc,
        (
            gcloud_exceptions.ServiceUnavailable,
            gcloud_exceptions.DeadlineExceeded,
            gcloud_exceptions.InternalServerError,
            gcloud_exceptions.RetryError,
        ),
    ):
        return True
    message = str(exc).lower()
    keywords = (
        "dns resolution failed",
        "could not contact dns servers",
        "statuscode.unavailable",
        "deadline exceeded",
        "timed out",
        "temporarily unavailable",
    )
    return any(key in message for key in keywords)


def iter_collection_docs(collection, page_size: int, max_retries: int):
    query = collection.order_by("__name__").limit(page_size)
    last_doc = None
    while True:
        current_query = query.start_after(last_doc) if last_doc is not None else query
        docs = None
        for attempt in range(max_retries + 1):
            try:
                docs = list(current_query.stream(timeout=120))
                break
            except Exception as exc:  # pragma: no cover - network dependent
                if not is_retryable_stream_error(exc) or attempt >= max_retries:
                    raise
                sleep_seconds = min(2**attempt, 30)
                print(
                    f"Read page failed ({exc}); retry {attempt + 1}/{max_retries} "
                    f"after {sleep_seconds}s."
                )
                time.sleep(sleep_seconds)
        if not docs:
            break
        for doc in docs:
            yield doc
        last_doc = docs[-1]


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
    if args.read_page_size <= 0:
        print("read-page-size must be 1 or greater.", file=sys.stderr)
        return 2
    if args.read_max_retries < 0:
        print("read-max-retries must be 0 or greater.", file=sys.stderr)
        return 2

    client = get_client(args.project_id, args.credentials or None)
    collection = client.collection("equipment")

    total = 0
    updated = 0
    skipped = 0
    errors = 0
    pending = 0
    batch = client.batch()
    collect_stats = (
        args.write_summary
        or args.write_ui_filters
        or args.write_prefecture_orgs
        or args.write_data_version
    )
    prefecture_counts: Dict[str, int] = {}
    prefecture_orgs: Dict[str, set[str]] = {}
    prefecture_org_counts: Dict[str, Dict[str, int]] = {}
    all_categories: set[str] = set()
    region_categories: Dict[str, set[str]] = {}

    for doc in iter_collection_docs(
        collection=collection,
        page_size=args.read_page_size,
        max_retries=args.read_max_retries,
    ):
        total += 1
        try:
            data = doc.to_dict() or {}
            updates = build_updates(
                data,
                force_tokens=args.force_tokens,
                force_aliases=args.force_aliases,
                include_region=not args.skip_region,
            )
            if collect_stats:
                org_name = str(data.get("org_name", "") or "").strip()
                prefecture = str(data.get("prefecture", "") or "").strip()
                if not prefecture:
                    prefecture = guess_prefecture(data.get("address_raw", "") or org_name).strip()
                region = str(data.get("region", "") or "").strip()
                if not region and prefecture:
                    region = resolve_region(prefecture).strip()
                category_general = str(data.get("category_general", "") or "").strip()

                if prefecture:
                    prefecture_counts[prefecture] = prefecture_counts.get(prefecture, 0) + 1
                    if org_name:
                        prefecture_orgs.setdefault(prefecture, set()).add(org_name)
                        org_counts = prefecture_org_counts.setdefault(prefecture, {})
                        org_counts[org_name] = org_counts.get(org_name, 0) + 1
                if category_general:
                    all_categories.add(category_general)
                    if region:
                        region_categories.setdefault(region, set()).add(category_general)
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

    if collect_stats:
        updated_at = datetime.now(timezone.utc).isoformat()
    else:
        updated_at = ""

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
            "updated_at": updated_at,
        }
        if args.dry_run:
            print(f"Summary preview: {top_prefectures}")
        else:
            client.collection("stats").document(args.summary_doc).set(summary_data)

    if args.write_ui_filters:
        region_categories_payload = {
            region: sorted_unique(categories)
            for region, categories in region_categories.items()
        }
        ui_filters_data = {
            "all_categories": sorted_unique(all_categories),
            "region_categories": region_categories_payload,
            "updated_at": updated_at,
        }
        if args.dry_run:
            print(
                "UI filters preview: "
                f"regions={len(region_categories_payload)} "
                f"all_categories={len(ui_filters_data['all_categories'])}"
            )
        else:
            client.collection("stats").document(args.ui_filters_doc).set(ui_filters_data)

    if args.write_prefecture_orgs:
        parent_ref = client.collection("stats").document(args.prefecture_orgs_doc)
        prefectures = sorted(prefecture_org_counts.keys())
        parent_payload = {
            "prefectures": prefectures,
            "updated_at": updated_at,
        }
        if args.dry_run:
            print(f"Prefecture orgs preview: prefectures={len(prefectures)}")
        else:
            parent_ref.set(parent_payload, merge=True)
        for prefecture in prefectures:
            org_counts = prefecture_org_counts[prefecture]
            org_list = sorted(
                [
                    {"org_name": org_name, "count": int(count)}
                    for org_name, count in org_counts.items()
                ],
                key=lambda item: (-item["count"], item["org_name"]),
            )
            doc_payload = {
                "prefecture": prefecture,
                "total_equipment": int(sum(org_counts.values())),
                "total_facilities": int(len(org_counts)),
                "org_list": org_list,
                "updated_at": updated_at,
            }
            if args.dry_run:
                continue
            parent_ref.collection(args.prefecture_orgs_subcollection).document(prefecture).set(
                doc_payload
            )

    if args.write_data_version:
        equipment_total = int(sum(prefecture_counts.values())) if collect_stats else int(total)
        data_version_value = f"{updated_at}:{equipment_total}:{updated}"
        data_version_payload = {
            "version": data_version_value,
            "updated_at": updated_at,
            "equipment_total": equipment_total,
            "partial_run": bool(args.limit),
        }
        if args.dry_run:
            print(f"Data version preview: {data_version_value}")
        else:
            client.collection("stats").document(args.data_version_doc).set(data_version_payload)

    print(
        f"Done. processed={total} updated={updated} skipped={skipped} errors={errors}"
    )
    return 0


def main() -> None:
    args = parse_args(sys.argv[1:])
    sys.exit(run_backfill(args))


if __name__ == "__main__":
    main()
