from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
from bs4 import BeautifulSoup
from google.api_core import exceptions as gcloud_exceptions

from .eqnet_backfill import EQNET_SEARCH_URL, parse_eqnet_id, strip_html_wrapper
from .firestore_client import get_client

EQNET_PUBLIC_EQUIPMENT_URL = "https://eqnet.jp/public/equipment.html"

DEFAULT_LARGE_CATEGORIES_OUT = "crawler/eqnet_large_categories.csv"
DEFAULT_CATEGORIES_OUT = "crawler/eqnet_categories.csv"
DEFAULT_EQUIPMENT_MAP_OUT = "crawler/eqnet_category_equipment_map.csv"
DEFAULT_UPDATE_PREVIEW_OUT = "crawler/eqnet_category_update_preview.csv"

SPACE_RE = re.compile(r"\s+")
CATEGORY_COUNT_RE = re.compile(r"\((\d+)\s*台\)")
GLOBAL_CATEGORIES_RE = re.compile(
    r"Global\.categories\s*=\s*(\[[\s\S]*?\])\s*\|\|\s*\[\];", re.MULTILINE
)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync EQNET category hierarchy and apply category updates to Firestore."
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
        "--timeout",
        type=float,
        default=30.0,
        help="Request timeout seconds.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="Seconds to sleep between category fetch requests.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Firestore batch write size (1-500).",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=200,
        help="Progress log interval for Firestore documents.",
    )
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Export EQNET category CSVs and mapping only. Firestore is not read or written.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read Firestore and generate update preview without writing.",
    )
    parser.add_argument(
        "--large-categories-out",
        default=DEFAULT_LARGE_CATEGORIES_OUT,
        help=f"Output CSV path for large categories (default: {DEFAULT_LARGE_CATEGORIES_OUT}).",
    )
    parser.add_argument(
        "--categories-out",
        default=DEFAULT_CATEGORIES_OUT,
        help=f"Output CSV path for categories (default: {DEFAULT_CATEGORIES_OUT}).",
    )
    parser.add_argument(
        "--equipment-map-out",
        default=DEFAULT_EQUIPMENT_MAP_OUT,
        help=f"Output CSV path for equipment category map (default: {DEFAULT_EQUIPMENT_MAP_OUT}).",
    )
    parser.add_argument(
        "--update-preview-out",
        default=DEFAULT_UPDATE_PREVIEW_OUT,
        help=f"Output CSV path for Firestore update preview (default: {DEFAULT_UPDATE_PREVIEW_OUT}).",
    )
    return parser.parse_args(list(argv))


def clean_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = SPACE_RE.sub(" ", text).strip()
    return text


def strip_category_count_suffix(text: str) -> str:
    normalized = clean_text(text)
    return CATEGORY_COUNT_RE.sub("", normalized).strip()


def extract_category_count(text: str) -> int:
    match = CATEGORY_COUNT_RE.search(clean_text(text))
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return 0


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def fetch_public_equipment_html(session: requests.Session, timeout: float) -> str:
    return fetch_url_text(session=session, url=EQNET_PUBLIC_EQUIPMENT_URL, timeout=timeout)


def fetch_url_text(session: requests.Session, url: str, timeout: float) -> str:
    request_errors: list[str] = []
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        return response.text
    except requests.RequestException as first_error:
        request_errors.append(str(first_error))

    # Fallback to curl for environments where Python DNS resolution is unstable.
    max_time = str(max(1, int(timeout)))
    for attempt in range(3):
        result = subprocess.run(
            [
                "curl",
                "-L",
                "-s",
                "--retry",
                "2",
                "--retry-delay",
                "1",
                "--retry-all-errors",
                "--max-time",
                max_time,
                url,
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout.decode("utf-8", errors="replace")
        request_errors.append(
            f"curl attempt {attempt + 1} rc={result.returncode} err={result.stderr.decode('utf-8', errors='replace')[:200]}"
        )
        if attempt < 2:
            time.sleep(attempt + 1)

    raise RuntimeError(f"failed requests+curl for {url}: {' | '.join(request_errors)}")


def parse_large_categories(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for option in soup.select('select[name="large_category_id"] option'):
        value_raw = clean_text(option.get("value", ""))
        if not value_raw:
            continue
        try:
            large_category_id = int(value_raw)
        except ValueError:
            continue
        if large_category_id in seen:
            continue
        seen.add(large_category_id)
        rows.append(
            {
                "large_category_id": large_category_id,
                "large_category_name": clean_text(option.get_text(" ", strip=True)),
            }
        )
    return rows


def parse_small_categories(html: str) -> list[dict[str, Any]]:
    match = GLOBAL_CATEGORIES_RE.search(html)
    if not match:
        raise RuntimeError("Global.categories was not found in EQNET public equipment HTML.")
    payload = json.loads(match.group(1))
    rows: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            category_id = int(item.get("value"))
            large_category_id = int(item.get("large_category_id"))
        except (TypeError, ValueError):
            continue
        category_name_raw = clean_text(item.get("text", ""))
        rows.append(
            {
                "category_id": category_id,
                "large_category_id": large_category_id,
                "category_name_raw": category_name_raw,
                "category_small_name": strip_category_count_suffix(category_name_raw),
                "equipment_count_hint": extract_category_count(category_name_raw),
            }
        )
    return rows


def fetch_category_rows(
    session: requests.Session,
    category_id: int,
    timeout: float,
) -> tuple[list[dict[str, Any]], int]:
    url = f"{EQNET_SEARCH_URL}?category_id={category_id}"
    payload_text = strip_html_wrapper(fetch_url_text(session=session, url=url, timeout=timeout))
    payload = json.loads(payload_text)
    data = payload.get("data") or {}
    rows = data.get("data") or []
    total = int(data.get("total") or len(rows))
    return rows, total


def choose_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    # Deterministic rule:
    # 1) higher category equipment count hint first
    # 2) smaller category_id first
    return max(candidates, key=lambda item: (item["equipment_count_hint"], -item["category_id"]))


def build_eqnet_equipment_category_map(
    session: requests.Session,
    small_categories: list[dict[str, Any]],
    large_name_by_id: dict[int, str],
    timeout: float,
    sleep_seconds: float,
) -> tuple[dict[str, dict[str, Any]], int, int]:
    by_eqnet_id: dict[str, list[dict[str, Any]]] = {}
    request_errors = 0

    total_categories = len(small_categories)
    for index, category in enumerate(small_categories, start=1):
        category_id = category["category_id"]
        try:
            rows, query_total = fetch_category_rows(session, category_id=category_id, timeout=timeout)
        except Exception as exc:
            request_errors += 1
            print(
                f"[warn] category fetch failed: category_id={category_id} error={exc}",
                file=sys.stderr,
            )
            continue

        for row in rows:
            eqnet_equipment_id = parse_eqnet_id(row.get("id"))
            if not eqnet_equipment_id:
                continue
            candidates = by_eqnet_id.setdefault(eqnet_equipment_id, [])
            candidates.append(
                {
                    "eqnet_equipment_id": eqnet_equipment_id,
                    "large_category_id": category["large_category_id"],
                    "large_category_name": large_name_by_id.get(category["large_category_id"], ""),
                    "category_id": category_id,
                    "category_name_raw": category["category_name_raw"],
                    "category_small_name": category["category_small_name"],
                    "equipment_count_hint": category["equipment_count_hint"],
                    "source_total": query_total,
                }
            )

        if index % 20 == 0 or index == total_categories:
            print(f"Category fetch progress: {index}/{total_categories}")
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    selected_map: dict[str, dict[str, Any]] = {}
    conflicts = 0
    for eqnet_id, candidates in by_eqnet_id.items():
        if not candidates:
            continue
        selected = choose_candidate(candidates)
        candidate_count = len(candidates)
        if candidate_count > 1:
            conflicts += 1
            choices = ", ".join(
                f"{item['category_id']}:{item['category_small_name']}" for item in candidates[:6]
            )
            print(
                f"[conflict] eqnet_equipment_id={eqnet_id} candidate_count={candidate_count} "
                f"selected={selected['category_id']}:{selected['category_small_name']} "
                f"choices={choices}",
                file=sys.stderr,
            )
        selected_map[eqnet_id] = {
            **selected,
            "candidate_count": candidate_count,
            "has_conflict": candidate_count > 1,
        }
    return selected_map, conflicts, request_errors


def compose_existing_category_text(data: dict[str, Any]) -> str:
    old_general = clean_text(data.get("old_category_general", ""))
    old_detail = clean_text(data.get("old_category_detail", ""))
    current_general = clean_text(data.get("category_general", ""))
    current_detail = clean_text(data.get("category_detail", ""))

    base_general = old_general or current_general
    base_detail = old_detail or current_detail

    if base_general and base_detail:
        return f"{base_general} / {base_detail}"
    if base_general:
        return base_general
    if base_detail:
        return base_detail
    return "未分類"


def build_updates(
    data: dict[str, Any],
    mapping: dict[str, dict[str, Any]],
    now_iso: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    before_general = clean_text(data.get("category_general", ""))
    before_detail = clean_text(data.get("category_detail", ""))
    eqnet_equipment_id = parse_eqnet_id(data.get("eqnet_equipment_id") or data.get("eqnet_url"))

    matched = bool(eqnet_equipment_id and eqnet_equipment_id in mapping)
    if matched:
        selected = mapping[eqnet_equipment_id]
        new_general = clean_text(selected.get("large_category_name", "")) or "その他"
        new_detail = clean_text(selected.get("category_small_name", "")) or "未分類"
        eqnet_large_id = str(selected.get("large_category_id", ""))
        eqnet_category_id = str(selected.get("category_id", ""))
        fallback = False
    else:
        new_general = "その他"
        new_detail = compose_existing_category_text(data)
        eqnet_large_id = ""
        eqnet_category_id = ""
        fallback = True

    updates = {
        "category_general": new_general,
        "category_detail": new_detail,
        "eqnet_category_large_id": eqnet_large_id,
        "eqnet_category_id": eqnet_category_id,
        "eqnet_category_source": "eqnet_public_equipment",
        "eqnet_category_synced_at": now_iso,
        "eqnet_category_fallback": fallback,
        "category_general_before_sync": before_general,
        "category_detail_before_sync": before_detail,
    }
    summary = {
        "eqnet_equipment_id": eqnet_equipment_id,
        "status": "matched" if matched else "fallback",
        "before_general": before_general,
        "before_detail": before_detail,
        "new_general": new_general,
        "new_detail": new_detail,
        "category_changed": before_general != new_general or before_detail != new_detail,
        "fallback": fallback,
    }
    return updates, summary


def commit_batch_with_retry(
    batch: Any,
    doc_ids: list[str],
    max_retries: int = 3,
    base_sleep_seconds: float = 1.0,
) -> tuple[bool, str]:
    for attempt in range(max_retries):
        try:
            batch.commit()
            return True, ""
        except (
            gcloud_exceptions.GoogleAPICallError,
            gcloud_exceptions.RetryError,
            gcloud_exceptions.ServiceUnavailable,
        ) as exc:
            if attempt >= max_retries - 1:
                return False, f"{exc}"
            time.sleep(base_sleep_seconds * (attempt + 1))
        except Exception as exc:  # pragma: no cover - defensive fallback
            if attempt >= max_retries - 1:
                return False, f"{exc}"
            time.sleep(base_sleep_seconds * (attempt + 1))
    return False, f"unknown error for {len(doc_ids)} docs"


def run(args: argparse.Namespace) -> int:
    if args.export_only and args.dry_run:
        print("--export-only and --dry-run cannot be used together.", file=sys.stderr)
        return 2
    if args.batch_size <= 0 or args.batch_size > 500:
        print("batch-size must be between 1 and 500.", file=sys.stderr)
        return 2
    if not args.export_only and not args.project_id:
        print("Missing --project-id or KIKIDOKO_PROJECT_ID.", file=sys.stderr)
        return 2

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "kikidoko-eqnet-category-sync/0.1",
            "Accept": "application/json,text/plain,*/*",
        }
    )

    try:
        html = fetch_public_equipment_html(session=session, timeout=args.timeout)
    except Exception as exc:
        print(f"Failed to fetch EQNET public equipment page: {exc}", file=sys.stderr)
        return 1

    large_categories = parse_large_categories(html)
    small_categories = parse_small_categories(html)
    large_name_by_id = {row["large_category_id"]: row["large_category_name"] for row in large_categories}

    for row in small_categories:
        row["large_category_name"] = large_name_by_id.get(row["large_category_id"], "")

    large_categories_out = Path(args.large_categories_out)
    categories_out = Path(args.categories_out)
    equipment_map_out = Path(args.equipment_map_out)
    update_preview_out = Path(args.update_preview_out)

    write_csv(
        large_categories_out,
        fieldnames=["large_category_id", "large_category_name"],
        rows=large_categories,
    )
    write_csv(
        categories_out,
        fieldnames=[
            "category_id",
            "category_name_raw",
            "category_small_name",
            "equipment_count_hint",
            "large_category_id",
            "large_category_name",
        ],
        rows=small_categories,
    )
    print(
        f"Exported categories: large={len(large_categories)} small={len(small_categories)} "
        f"({large_categories_out}, {categories_out})"
    )

    eqnet_map, conflict_count, request_errors = build_eqnet_equipment_category_map(
        session=session,
        small_categories=small_categories,
        large_name_by_id=large_name_by_id,
        timeout=args.timeout,
        sleep_seconds=args.sleep,
    )
    map_rows = sorted(eqnet_map.values(), key=lambda item: int(item["eqnet_equipment_id"]))
    write_csv(
        equipment_map_out,
        fieldnames=[
            "eqnet_equipment_id",
            "large_category_id",
            "large_category_name",
            "category_id",
            "category_name_raw",
            "category_small_name",
            "equipment_count_hint",
            "source_total",
            "candidate_count",
            "has_conflict",
        ],
        rows=map_rows,
    )
    print(
        f"Built EQNET equipment map: mapped={len(eqnet_map)} conflicts={conflict_count} "
        f"request_errors={request_errors} ({equipment_map_out})"
    )

    if args.export_only:
        print("Export-only mode completed. Firestore was not touched.")
        return 0

    client = get_client(args.project_id, args.credentials or None)
    collection = client.collection("equipment")
    now_iso = datetime.now(timezone.utc).isoformat()

    ensure_parent(update_preview_out)
    preview_fields = [
        "doc_id",
        "equipment_id",
        "name",
        "org_name",
        "eqnet_equipment_id",
        "status",
        "before_general",
        "before_detail",
        "new_general",
        "new_detail",
        "category_changed",
        "fallback",
    ]

    stats = {
        "total_docs": 0,
        "matched_docs": 0,
        "fallback_docs": 0,
        "category_changed_docs": 0,
        "category_unchanged_docs": 0,
    }
    failed_doc_ids: list[str] = []

    with update_preview_out.open("w", newline="", encoding="utf-8") as fh:
        preview_writer = csv.DictWriter(fh, fieldnames=preview_fields)
        preview_writer.writeheader()

        batch = client.batch()
        pending_doc_ids: list[str] = []

        for doc in collection.stream():
            data = doc.to_dict() or {}
            updates, summary = build_updates(data=data, mapping=eqnet_map, now_iso=now_iso)

            stats["total_docs"] += 1
            if summary["status"] == "matched":
                stats["matched_docs"] += 1
            else:
                stats["fallback_docs"] += 1
            if summary["category_changed"]:
                stats["category_changed_docs"] += 1
            else:
                stats["category_unchanged_docs"] += 1

            preview_writer.writerow(
                {
                    "doc_id": doc.id,
                    "equipment_id": clean_text(data.get("equipment_id", "")),
                    "name": clean_text(data.get("name", "")),
                    "org_name": clean_text(data.get("org_name", "")),
                    "eqnet_equipment_id": summary["eqnet_equipment_id"],
                    "status": summary["status"],
                    "before_general": summary["before_general"],
                    "before_detail": summary["before_detail"],
                    "new_general": summary["new_general"],
                    "new_detail": summary["new_detail"],
                    "category_changed": summary["category_changed"],
                    "fallback": summary["fallback"],
                }
            )

            if not args.dry_run:
                batch.set(doc.reference, updates, merge=True)
                pending_doc_ids.append(doc.id)
                if len(pending_doc_ids) >= args.batch_size:
                    ok, message = commit_batch_with_retry(batch=batch, doc_ids=pending_doc_ids)
                    if not ok:
                        failed_doc_ids.extend(pending_doc_ids)
                        print(
                            f"[error] batch commit failed for {len(pending_doc_ids)} docs: {message}",
                            file=sys.stderr,
                        )
                    batch = client.batch()
                    pending_doc_ids = []

            if args.log_every > 0 and stats["total_docs"] % args.log_every == 0:
                print(
                    f"Firestore progress: processed={stats['total_docs']} matched={stats['matched_docs']} "
                    f"fallback={stats['fallback_docs']} changed={stats['category_changed_docs']}"
                )

        if not args.dry_run and pending_doc_ids:
            ok, message = commit_batch_with_retry(batch=batch, doc_ids=pending_doc_ids)
            if not ok:
                failed_doc_ids.extend(pending_doc_ids)
                print(
                    f"[error] final batch commit failed for {len(pending_doc_ids)} docs: {message}",
                    file=sys.stderr,
                )

    print(f"Update preview CSV: {update_preview_out}")
    print(
        f"Summary: total={stats['total_docs']} matched={stats['matched_docs']} "
        f"fallback={stats['fallback_docs']} changed={stats['category_changed_docs']} "
        f"unchanged={stats['category_unchanged_docs']} conflicts={conflict_count} "
        f"request_errors={request_errors}"
    )

    if failed_doc_ids:
        print(
            f"[error] Firestore commit failed docs: count={len(failed_doc_ids)} "
            f"sample={','.join(failed_doc_ids[:20])}",
            file=sys.stderr,
        )
        return 1

    if args.dry_run:
        print("Dry-run completed. Firestore was not written.")
    else:
        print("Firestore category sync completed.")
    return 0


def main() -> None:
    args = parse_args(sys.argv[1:])
    sys.exit(run(args))


if __name__ == "__main__":
    main()
