from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path
from typing import Any, Iterable

from .firestore_client import get_client
from .paper_abstract_sources import clean_abstract_text, normalize_doi

PRIORITY_RULES: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (1, "SEM/FIB/イオンミリング", ("sem", "fib", "ion milling", "イオンミリング", "電子顕微鏡", "走査電子")),
    (2, "NMR/ESR", ("nmr", "esr", "核磁気", "電子スピン")),
    (3, "XRD/XPS", ("xrd", "xps", "x線回折", "x線光電子", "x-ray diffraction")),
    (4, "LC-MS/GC-MS", ("lc-ms", "gc-ms", "mass spect", "クロマト", "質量分析")),
    (5, "TEM/AFM", ("tem", "afm", "透過電子", "原子間力", "透過型電子")),
)


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build manual curation queue CSV for equipment usage review.",
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
        "--limit",
        type=int,
        default=500,
        help="Number of rows to output (default: 500).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=300,
        help="Firestore read page size (default: 300).",
    )
    parser.add_argument(
        "--max-abstract-chars",
        type=int,
        default=500,
        help="Max characters per abstract column in CSV (default: 500).",
    )
    parser.add_argument(
        "--output",
        default="crawler/manual_curation_queue_500.csv",
        help="Output CSV path.",
    )
    return parser.parse_args(list(argv))


def resolve_workspace_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    if path.exists():
        return path
    return Path(__file__).resolve().parents[3] / path


def normalize_text(value: Any) -> str:
    return clean_abstract_text(str(value or ""))


def classify_priority(item: dict[str, Any]) -> tuple[int, str]:
    category_general = normalize_text(item.get("category_general"))
    category_detail = normalize_text(item.get("category_detail"))
    name = normalize_text(item.get("name"))
    corpus = f"{name} {category_general} {category_detail}".lower()

    for priority, label, keywords in PRIORITY_RULES:
        if any(keyword.lower() in corpus for keyword in keywords):
            return priority, label
    return 99, "その他"


def trim_text(value: str, max_chars: int) -> str:
    text = normalize_text(value)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def top_three_papers(raw_papers: Any, max_chars: int) -> list[dict[str, str]]:
    if not isinstance(raw_papers, list):
        return []
    papers: list[dict[str, str]] = []
    for paper in raw_papers:
        if not isinstance(paper, dict):
            continue
        doi = normalize_doi(str(paper.get("doi", "")))
        if not doi:
            continue
        papers.append(
            {
                "doi": doi,
                "title": normalize_text(paper.get("title")),
                "year": normalize_text(paper.get("year")),
                "abstract": trim_text(str(paper.get("abstract", "")), max_chars),
            }
        )
        if len(papers) >= 3:
            break
    return papers


def fetch_all_docs(collection, page_size: int):
    last_doc = None
    while True:
        query = collection.order_by("__name__").limit(page_size)
        if last_doc is not None:
            query = query.start_after(last_doc)
        docs = list(query.stream())
        if not docs:
            break
        for doc in docs:
            yield doc
        last_doc = docs[-1]


def run(args: argparse.Namespace) -> int:
    if not args.project_id:
        print("Missing --project-id or KIKIDOKO_PROJECT_ID.", file=sys.stderr)
        return 2
    if args.limit <= 0:
        print("limit must be greater than 0.", file=sys.stderr)
        return 2
    if args.page_size <= 0:
        print("page-size must be greater than 0.", file=sys.stderr)
        return 2
    if args.max_abstract_chars <= 50:
        print("max-abstract-chars must be greater than 50.", file=sys.stderr)
        return 2

    client = get_client(args.project_id, args.credentials or None)
    collection = client.collection("equipment")

    candidates: list[dict[str, Any]] = []
    scanned_docs = 0

    for doc in fetch_all_docs(collection, args.page_size):
        scanned_docs += 1
        data = doc.to_dict() or {}
        papers_status = str(data.get("papers_status", "") or "")
        papers = data.get("papers")
        if papers_status != "ready" or not isinstance(papers, list) or len(papers) == 0:
            continue

        if str(data.get("usage_manual_editor", "") or "").strip().lower() == "manual":
            continue

        top_papers = top_three_papers(papers, args.max_abstract_chars)
        if not top_papers:
            continue

        priority_group, priority_label = classify_priority(data)
        candidates.append(
            {
                "doc_id": doc.id,
                "name": normalize_text(data.get("name")),
                "org_name": normalize_text(data.get("org_name")),
                "category_general": normalize_text(data.get("category_general")),
                "category_detail": normalize_text(data.get("category_detail")),
                "papers_count": len(papers),
                "priority_group": priority_group,
                "priority_label": priority_label,
                "papers": top_papers,
            }
        )

    candidates.sort(
        key=lambda item: (
            item["priority_group"],
            -int(item.get("papers_count", 0)),
            item.get("name", ""),
            item.get("doc_id", ""),
        )
    )

    selected = candidates[: args.limit]

    fieldnames = [
        "priority_rank",
        "priority_group",
        "priority_label",
        "doc_id",
        "name",
        "org_name",
        "category_general",
        "category_detail",
        "papers_count",
        "doi_1",
        "title_1",
        "year_1",
        "abstract_1",
        "doi_2",
        "title_2",
        "year_2",
        "abstract_2",
        "doi_3",
        "title_3",
        "year_3",
        "abstract_3",
    ]

    output_path = resolve_workspace_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for idx, item in enumerate(selected, start=1):
            row = {
                "priority_rank": idx,
                "priority_group": item["priority_group"],
                "priority_label": item["priority_label"],
                "doc_id": item["doc_id"],
                "name": item["name"],
                "org_name": item["org_name"],
                "category_general": item["category_general"],
                "category_detail": item["category_detail"],
                "papers_count": item["papers_count"],
            }
            papers = item["papers"]
            for paper_index in range(3):
                paper = papers[paper_index] if paper_index < len(papers) else {}
                suffix = str(paper_index + 1)
                row[f"doi_{suffix}"] = paper.get("doi", "")
                row[f"title_{suffix}"] = paper.get("title", "")
                row[f"year_{suffix}"] = paper.get("year", "")
                row[f"abstract_{suffix}"] = paper.get("abstract", "")
            writer.writerow(row)

    print(
        (
            f"Done manual_curation_queue. scanned_docs={scanned_docs} candidates={len(candidates)} "
            f"selected={len(selected)} output={output_path}"
        )
    )
    return 0


def main() -> None:
    args = parse_args(sys.argv[1:])
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
