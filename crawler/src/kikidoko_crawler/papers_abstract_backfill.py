from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests

from .firestore_client import get_client
from .paper_abstract_sources import (
    clean_abstract_text,
    normalize_doi,
    resolve_abstract_for_paper,
)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill paper abstracts into equipment.papers[].",
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
        "--elsevier-api-key",
        default=os.getenv("ELSEVIER_API_KEY", ""),
        help="Elsevier API key (or set ELSEVIER_API_KEY).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout seconds (default: 30).",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.12,
        help="Sleep seconds after each DOI lookup.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Firestore batch write size (default: 100, max: 500).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=250,
        help="Firestore read page size (default: 250).",
    )
    parser.add_argument(
        "--limit-docs",
        type=int,
        default=0,
        help="Process at most N matching docs (0 = no limit).",
    )
    parser.add_argument(
        "--start-after-doc-id",
        default="",
        help="Resume from document id (exclusive).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Refetch even if papers[].abstract already exists.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write updates to Firestore.",
    )
    parser.add_argument(
        "--result-csv",
        default="crawler/papers_abstract_result.csv",
        help="Result CSV path (default: crawler/papers_abstract_result.csv).",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=50,
        help="Print progress every N docs (default: 50).",
    )
    parser.add_argument(
        "--flush-logs",
        action="store_true",
        help="Force flush logs after each progress output.",
    )
    return parser.parse_args(list(argv))


def resolve_workspace_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    if path.exists():
        return path
    return Path(__file__).resolve().parents[3] / path


def write_result_csv(path_value: str, rows: list[dict[str, Any]]) -> Path:
    output_path = resolve_workspace_path(path_value)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["doc_id", "doi", "source", "status", "error"]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return output_path


def commit_batch(batch, pending: int, sleep_seconds: float) -> None:
    if pending <= 0:
        return
    batch.commit()
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)


def fetch_page(query, retries: int = 4):
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            return list(query.stream())
        except Exception as exc:  # pragma: no cover - defensive
            last_error = exc
            time.sleep(1.5 + attempt * 1.2)
    if last_error:
        raise last_error
    return []


def run(args: argparse.Namespace) -> int:
    if not args.project_id:
        print("Missing --project-id or KIKIDOKO_PROJECT_ID.", file=sys.stderr)
        return 2
    if args.batch_size <= 0 or args.batch_size > 500:
        print("batch-size must be between 1 and 500.", file=sys.stderr)
        return 2
    if args.page_size <= 0:
        print("page-size must be 1 or greater.", file=sys.stderr)
        return 2
    if args.sleep < 0:
        print("sleep must be 0 or greater.", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("timeout must be greater than 0.", file=sys.stderr)
        return 2

    client = get_client(args.project_id, args.credentials or None)
    collection = client.collection("equipment")
    session = requests.Session()
    doi_cache: dict[str, dict[str, Any]] = {}
    result_rows: list[dict[str, Any]] = []

    scanned_docs = 0
    target_docs = 0
    updated_docs = 0
    papers_checked = 0
    papers_changed = 0
    papers_filled = 0
    fallback_count = 0
    error_count = 0

    pending = 0
    batch = client.batch()
    last_doc = None
    start_after_snapshot = None
    if args.start_after_doc_id:
        try:
            start_candidate = collection.document(args.start_after_doc_id).get()
            if start_candidate.exists:
                start_after_snapshot = start_candidate
        except Exception as exc:  # pragma: no cover - defensive
            print(f"Failed to resolve --start-after-doc-id: {exc}", file=sys.stderr)

    while True:
        page_query = collection.order_by("__name__").limit(args.page_size)
        if last_doc is not None:
            page_query = page_query.start_after(last_doc)
        elif start_after_snapshot is not None:
            page_query = page_query.start_after(start_after_snapshot)
        docs = fetch_page(page_query)
        if not docs:
            break

        for doc in docs:
            scanned_docs += 1
            if args.start_after_doc_id and start_after_snapshot is None and doc.id <= args.start_after_doc_id:
                continue

            data = doc.to_dict() or {}
            papers_status = str(data.get("papers_status", "") or "")
            papers = data.get("papers")
            if papers_status != "ready" or not isinstance(papers, list) or len(papers) == 0:
                continue

            target_docs += 1
            now_iso = datetime.now(timezone.utc).isoformat()
            doc_changed = False
            doc_total = 0
            doc_filled = 0
            doc_errors = 0
            next_papers: list[Any] = []

            for paper in papers:
                if not isinstance(paper, dict):
                    next_papers.append(paper)
                    continue

                doc_total += 1
                papers_checked += 1
                current_abstract = clean_abstract_text(str(paper.get("abstract", "")))
                if current_abstract and not args.force:
                    doc_filled += 1
                    next_papers.append(paper)
                    continue

                normalized = normalize_doi(str(paper.get("doi", "")))
                cache_key = normalized
                if cache_key and cache_key in doi_cache:
                    resolved = doi_cache[cache_key]
                else:
                    resolved = resolve_abstract_for_paper(
                        session=session,
                        paper=paper,
                        elsevier_api_key=args.elsevier_api_key,
                        timeout=args.timeout,
                    )
                    if cache_key:
                        doi_cache[cache_key] = resolved
                    if args.sleep > 0:
                        time.sleep(args.sleep)

                abstract_text = clean_abstract_text(str(resolved.get("abstract", "")))
                source = str(resolved.get("source", "") or "missing")
                status = str(resolved.get("status", "") or "")
                error = str(resolved.get("error", "") or "")

                updated_paper = dict(paper)
                updated_paper["abstract"] = abstract_text
                updated_paper["abstract_source"] = source
                updated_paper["abstract_updated_at"] = now_iso

                if "abstract_ja_auto_fallback" not in updated_paper:
                    updated_paper["abstract_ja_auto_fallback"] = False

                next_papers.append(updated_paper)
                doc_changed = True
                papers_changed += 1

                if abstract_text:
                    doc_filled += 1
                    papers_filled += 1
                if source == "fallback":
                    fallback_count += 1
                if status == "missing":
                    doc_errors += 1
                if status == "error":
                    doc_errors += 1
                    error_count += 1

                result_rows.append(
                    {
                        "doc_id": doc.id,
                        "doi": normalized,
                        "source": source,
                        "status": status,
                        "error": error,
                    }
                )

            if doc_total == 0:
                continue

            doc_abstract_status = "ready"
            if doc_filled <= 0:
                doc_abstract_status = "error" if doc_errors > 0 else "missing"
            elif doc_filled < doc_total:
                doc_abstract_status = "partial"

            updates = {
                "papers": next_papers if doc_changed else papers,
                "papers_abstract_status": doc_abstract_status,
                "papers_abstract_total": doc_total,
                "papers_abstract_filled": doc_filled,
                "papers_abstract_updated_at": now_iso,
            }

            existing_total = int(data.get("papers_abstract_total", 0) or 0)
            existing_filled = int(data.get("papers_abstract_filled", 0) or 0)
            existing_status = str(data.get("papers_abstract_status", "") or "")
            need_stats_update = (
                existing_total != doc_total
                or existing_filled != doc_filled
                or existing_status != doc_abstract_status
                or not str(data.get("papers_abstract_updated_at", "") or "").strip()
            )

            if doc_changed or need_stats_update:
                updated_docs += 1
                if not args.dry_run:
                    batch.update(doc.reference, updates)
                    pending += 1
                    if pending >= args.batch_size:
                        commit_batch(batch, pending, args.sleep)
                        batch = client.batch()
                        pending = 0

            if args.log_every and target_docs % args.log_every == 0:
                print(
                    (
                        f"Processed target docs={target_docs} updated={updated_docs} "
                        f"papers_changed={papers_changed} fallback={fallback_count} errors={error_count}"
                    ),
                    flush=args.flush_logs,
                )

            if args.limit_docs and target_docs >= args.limit_docs:
                break

        last_doc = docs[-1]
        if args.limit_docs and target_docs >= args.limit_docs:
            break

    if not args.dry_run and pending:
        commit_batch(batch, pending, args.sleep)

    output_path = write_result_csv(args.result_csv, result_rows)
    print(
        (
            f"Done papers_abstract_backfill. scanned_docs={scanned_docs} target_docs={target_docs} "
            f"updated_docs={updated_docs} papers_checked={papers_checked} papers_changed={papers_changed} "
            f"papers_filled={papers_filled} fallback={fallback_count} errors={error_count} "
            f"result_csv={output_path}"
        ),
        flush=args.flush_logs,
    )
    return 0


def main() -> None:
    args = parse_args(sys.argv[1:])
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
