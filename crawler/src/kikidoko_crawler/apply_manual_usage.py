from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Iterable

from .firestore_client import get_client
from .paper_abstract_sources import clean_abstract_text, normalize_doi


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


def build_doc_override_map(overrides: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    doc_map: dict[str, dict[str, Any]] = {}
    for entry in overrides:
        if not isinstance(entry, dict):
            continue
        doc_id = str(entry.get("doc_id", "") or "").strip()
        if not doc_id:
            print("Skipped entry without doc_id.", file=sys.stderr)
            continue
        # Last entry for the same doc_id wins.
        doc_map[doc_id] = entry
    return doc_map


def normalize_text_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [clean_abstract_text(str(item)) for item in raw if clean_abstract_text(str(item))]


def build_paper_abstract_map(raw: Any) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not isinstance(raw, list):
        return mapping
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        doi = normalize_doi(str(entry.get("doi", "")))
        if not doi or "abstract_ja" not in entry:
            continue
        abstract_ja = clean_abstract_text(str(entry.get("abstract_ja", "")))
        mapping[doi] = abstract_ja
    return mapping


def apply_paper_abstract_overrides(
    papers: Any,
    abstract_map: dict[str, str],
    generated_at: str,
) -> tuple[list[Any] | None, int]:
    if not isinstance(papers, list):
        return None, 0
    if not abstract_map:
        return list(papers), 0

    updated_papers: list[Any] = []
    matched = 0
    for paper in papers:
        if not isinstance(paper, dict):
            updated_papers.append(paper)
            continue

        updated = dict(paper)
        doi = normalize_doi(str(updated.get("doi", "")))
        if doi in abstract_map:
            abstract_ja = abstract_map.get(doi, "")
            updated["abstract_ja"] = abstract_ja
            updated["abstract_ja_model"] = "manual-chat" if abstract_ja else ""
            updated["abstract_ja_generated_at"] = generated_at if abstract_ja else ""
            updated["abstract_ja_auto_fallback"] = False
            matched += 1
        updated_papers.append(updated)

    return updated_papers, matched


def main() -> None:
    args = parse_args(sys.argv[1:])
    if not args.project_id:
        print("Missing --project-id or KIKIDOKO_PROJECT_ID.", file=sys.stderr)
        sys.exit(2)

    overrides = load_overrides(args.input)
    overrides_by_doc = build_doc_override_map(overrides)

    client = get_client(args.project_id, args.credentials or None)
    collection = client.collection("equipment")
    updated_at = datetime.now(timezone.utc).isoformat()

    applied_docs = 0
    skipped_docs = 0
    docs_with_paper_abstract_updates = 0
    paper_abstract_updates = 0

    for doc_id, entry in overrides_by_doc.items():
        summary = clean_abstract_text(str(entry.get("summary", "")))
        bullets = normalize_text_list(entry.get("bullets"))
        sources = normalize_text_list(entry.get("source_titles"))
        dois_raw = entry.get("source_dois")
        source_dois = (
            [normalize_doi(str(item)) for item in dois_raw if normalize_doi(str(item))]
            if isinstance(dois_raw, list)
            else []
        )

        update: dict[str, Any] = {
            "usage_manual_summary": summary,
            "usage_manual_bullets": bullets,
            "usage_manual_sources": sources,
            "usage_manual_dois": source_dois,
            "usage_manual_editor": "manual",
            "usage_manual_updated_at": updated_at,
        }

        paper_abstract_map = build_paper_abstract_map(entry.get("paper_abstracts"))
        matched_abstracts = 0

        if paper_abstract_map:
            doc_snap = collection.document(doc_id).get()
            if doc_snap.exists:
                doc_data = doc_snap.to_dict() or {}
                updated_papers, matched_abstracts = apply_paper_abstract_overrides(
                    doc_data.get("papers"),
                    paper_abstract_map,
                    updated_at,
                )
                if updated_papers is not None and matched_abstracts > 0:
                    update["papers"] = updated_papers
                    docs_with_paper_abstract_updates += 1
                    paper_abstract_updates += matched_abstracts
            else:
                print(f"Skipped paper_abstracts for missing doc: {doc_id}", file=sys.stderr)

        if args.dry_run:
            print(
                f"[dry-run] {doc_id}: summary_len={len(summary)} bullets={len(bullets)} "
                f"paper_abstracts_matched={matched_abstracts}"
            )
            applied_docs += 1
            continue

        collection.document(doc_id).set(update, merge=True)
        applied_docs += 1
        print(f"Updated {doc_id} (paper_abstracts_matched={matched_abstracts})")

    skipped_docs = len(overrides) - len(overrides_by_doc)
    print(
        (
            f"Done apply_manual_usage. input_entries={len(overrides)} unique_docs={len(overrides_by_doc)} "
            f"applied_docs={applied_docs} skipped_entries={skipped_docs} "
            f"docs_with_paper_abstract_updates={docs_with_paper_abstract_updates} "
            f"paper_abstract_updates={paper_abstract_updates}"
        )
    )


if __name__ == "__main__":
    main()
