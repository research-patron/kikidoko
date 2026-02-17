from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .firestore_client import get_client

PENDING_READY_STATUSES = {"", "ready", "pending"}
UI_KNOWN_STATUSES = {
    "",
    "pending",
    "ready",
    "no_query",
    "no_results",
    "no_results_verified",
    "not_applicable_space",
    "error",
}


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit equipment documents that still look paper-pending in UI."
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
        "--output",
        default="crawler/papers_pending_audit.csv",
        help="Output CSV path (default: crawler/papers_pending_audit.csv).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=200,
        help="Number of documents per Firestore page.",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=500,
        help="Log progress every N scanned documents.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Stop after scanning this many documents (0=all).",
    )
    parser.add_argument(
        "--status",
        default="pending_like",
        help=(
            "Status filter: pending_like (default), no_results_verified, all, "
            "or comma-separated exact statuses."
        ),
    )
    return parser.parse_args(list(argv))


def is_papers_pending_record(papers_value: Any, status_value: Any) -> bool:
    status = str(status_value or "").strip()
    papers = papers_value if isinstance(papers_value, list) else []
    if papers:
        return False
    if status in PENDING_READY_STATUSES:
        return True
    if status not in UI_KNOWN_STATUSES:
        return True
    return False


def resolve_workspace_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    if path.exists():
        return path
    return Path(__file__).resolve().parents[3] / path


def fetch_page(query, retries: int = 3) -> List[Any]:
    last_error = None
    for attempt in range(retries):
        try:
            return list(query.stream())
        except Exception as exc:  # pragma: no cover - defensive
            last_error = exc
            time.sleep(2 + attempt * 2)
    if last_error:
        raise last_error
    return []


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "document_id",
        "equipment_id",
        "name",
        "org_name",
        "prefecture",
        "category_general",
        "category_detail",
        "papers_status",
        "papers_query",
        "papers_updated_at",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def run(args: argparse.Namespace) -> int:
    if not args.project_id:
        print("Missing --project-id or KIKIDOKO_PROJECT_ID.", file=sys.stderr)
        return 2
    if args.page_size <= 0:
        print("page-size must be 1 or greater.", file=sys.stderr)
        return 2

    client = get_client(args.project_id, args.credentials or None)
    collection = client.collection("equipment")

    status_filter = str(args.status or "pending_like").strip().lower()
    exact_statuses: set[str] | None = None
    if status_filter not in {"pending_like", "no_results_verified", "all"}:
        exact_statuses = {
            part.strip() for part in str(args.status).split(",") if part.strip()
        }
        if not exact_statuses:
            exact_statuses = None

    scanned = 0
    matched = 0
    status_counts: Dict[str, int] = {}
    rows: List[Dict[str, Any]] = []

    last_doc = None
    while True:
        query = collection.order_by("__name__").limit(args.page_size)
        if last_doc:
            query = query.start_after(last_doc)
        try:
            docs = fetch_page(query)
        except Exception as exc:
            print(f"Failed to fetch page: {exc}", file=sys.stderr)
            return 1
        if not docs:
            break
        for doc in docs:
            if args.limit and scanned >= args.limit:
                break
            scanned += 1
            data = doc.to_dict() or {}
            papers_status = str(data.get("papers_status", "") or "")
            papers = data.get("papers")
            is_match = False
            if status_filter == "pending_like":
                is_match = is_papers_pending_record(papers, papers_status)
            elif status_filter == "no_results_verified":
                is_match = papers_status == "no_results_verified"
            elif status_filter == "all":
                is_match = True
            else:
                is_match = papers_status in (exact_statuses or set())
            if not is_match:
                if args.log_every and scanned % args.log_every == 0:
                    print(f"Scanned {scanned} docs, matched {matched}.")
                continue
            matched += 1
            status_counts[papers_status] = status_counts.get(papers_status, 0) + 1
            rows.append(
                {
                    "document_id": doc.id,
                    "equipment_id": str(data.get("equipment_id", "") or ""),
                    "name": str(data.get("name", "") or ""),
                    "org_name": str(data.get("org_name", "") or ""),
                    "prefecture": str(data.get("prefecture", "") or ""),
                    "category_general": str(data.get("category_general", "") or ""),
                    "category_detail": str(data.get("category_detail", "") or ""),
                    "papers_status": papers_status,
                    "papers_query": str(data.get("papers_query", "") or ""),
                    "papers_updated_at": str(data.get("papers_updated_at", "") or ""),
                }
            )
            if args.log_every and scanned % args.log_every == 0:
                print(f"Scanned {scanned} docs, matched {matched}.")
        if args.limit and scanned >= args.limit:
            break
        last_doc = docs[-1]

    output_path = resolve_workspace_path(args.output)
    write_csv(output_path, rows)
    print(
        (
            f"Audit done. scanned={scanned} matched={matched} "
            f"status_filter={args.status} status_counts={status_counts} output={output_path}"
        )
    )
    return 0


def main() -> None:
    args = parse_args(sys.argv[1:])
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
