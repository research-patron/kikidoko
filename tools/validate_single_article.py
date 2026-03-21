#!/usr/bin/env python3
"""Validate one queue row before apply (single-item gate)."""

from __future__ import annotations

import argparse
import gzip
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from apply_manual_curation_batch import (
    count_chars,
    extract_known_dois,
    normalize_manual_content,
    normalize_text,
    row_payload,
)

DEFAULT_REVIEWER = "codex-manual"
INTERNAL_ID_PATTERN = re.compile(r"\beqnet-\d+\b", re.IGNORECASE)
PLACEHOLDER_DOI_PATTERN = re.compile(r"^10\.0000/", re.IGNORECASE)
DOI_TEXT_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_snapshot(path: Path) -> Dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def load_queue(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def load_timing_log(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def resolve_elapsed(timing_rows: List[Dict[str, Any]], doc_id: str, equipment_id: str) -> Optional[int]:
    doc_id = normalize_text(doc_id)
    equipment_id = normalize_text(equipment_id)
    for row in reversed(timing_rows):
        if normalize_text(row.get("doc_id")) != doc_id:
            continue
        row_equipment = normalize_text(row.get("equipment_id"))
        if equipment_id and row_equipment not in {"", equipment_id}:
            continue
        try:
            return int(row.get("elapsed_sec"))
        except Exception:
            return None
    return None


def find_item(snapshot_items: List[Dict[str, Any]], doc_id: str, equipment_id: str) -> Optional[Dict[str, Any]]:
    for item in snapshot_items:
        if not isinstance(item, dict):
            continue
        if doc_id and normalize_text(item.get("doc_id")) == doc_id:
            return item
    for item in snapshot_items:
        if not isinstance(item, dict):
            continue
        if equipment_id and normalize_text(item.get("equipment_id")) == equipment_id:
            return item
    return None


def beginner_non_ws_chars(manual: Dict[str, Any], mode: str) -> int:
    beginner = manual.get("beginner_guide") if isinstance(manual.get("beginner_guide"), dict) else {}
    text = "".join(
        [
            normalize_text(beginner.get("principle_ja")),
            normalize_text(beginner.get("sample_guidance_ja")),
            "".join(normalize_text(v) for v in beginner.get("basic_steps_ja") or []),
            "".join(normalize_text(v) for v in beginner.get("common_pitfalls_ja") or []),
        ]
    )
    return count_chars(text, mode)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate one manual article row")
    parser.add_argument("--snapshot", default="frontend/dist/equipment_snapshot.json.gz")
    parser.add_argument("--queue", default="tools/manual_curation_queue_beginner_1000.jsonl")
    parser.add_argument("--doc-id", default="")
    parser.add_argument("--reviewer", default=DEFAULT_REVIEWER)
    parser.add_argument("--min-beginner-chars", type=int, default=2000)
    parser.add_argument("--max-beginner-chars", type=int, default=3000)
    parser.add_argument("--char-count-mode", default="non_whitespace", choices=["non_whitespace", "raw"])
    parser.add_argument("--timing-log", default="tools/manual_item_timing_log.jsonl")
    parser.add_argument("--min-elapsed-sec", type=int, default=180)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    root = Path.cwd()
    snapshot_path = (root / args.snapshot).resolve()
    queue_path = (root / args.queue).resolve()
    timing_log_path = (root / args.timing_log).resolve()
    output_path = (root / args.output).resolve() if str(args.output or "").strip() else None

    snapshot = load_snapshot(snapshot_path)
    items = snapshot.get("items") if isinstance(snapshot.get("items"), list) else []
    queue = load_queue(queue_path)
    if not queue:
        raise ValueError("Queue is empty")

    target_row: Optional[Dict[str, Any]] = None
    doc_id_arg = normalize_text(args.doc_id)
    if doc_id_arg:
        for row in queue:
            if normalize_text(row.get("doc_id")) == doc_id_arg:
                target_row = row
                break
        if target_row is None:
            raise ValueError(f"Row not found for doc_id={doc_id_arg}")
    else:
        target_row = queue[0]

    doc_id = normalize_text(target_row.get("doc_id"))
    equipment_id = normalize_text(target_row.get("equipment_id"))
    item = find_item(items, doc_id, equipment_id)
    if item is None:
        raise ValueError(f"Snapshot item not found for doc_id={doc_id} equipment_id={equipment_id}")

    payload = row_payload(target_row, normalize_text(args.reviewer) or DEFAULT_REVIEWER)
    known_dois = extract_known_dois(item)
    normalized, issues = normalize_manual_content(
        payload,
        normalize_text(args.reviewer) or DEFAULT_REVIEWER,
        known_dois,
        beginner_min_chars=max(0, int(args.min_beginner_chars)),
        beginner_max_chars=max(0, int(args.max_beginner_chars)),
        char_count_mode=str(args.char_count_mode),
        doc_id=doc_id,
        equipment_id=equipment_id,
        equipment_name=normalize_text(item.get("name")),
        forbid_internal_id=True,
        forbid_placeholder_doi=True,
    )

    manual = normalized
    general = manual.get("general_usage") if isinstance(manual.get("general_usage"), dict) else {}
    beginner = manual.get("beginner_guide") if isinstance(manual.get("beginner_guide"), dict) else {}
    papers = manual.get("paper_explanations") if isinstance(manual.get("paper_explanations"), list) else []

    article_text = "".join(
        [
            normalize_text(general.get("summary_ja")),
            normalize_text(beginner.get("principle_ja")),
            normalize_text(beginner.get("sample_guidance_ja")),
            "".join(normalize_text(v) for v in beginner.get("basic_steps_ja") or []),
            "".join(normalize_text(v) for v in beginner.get("common_pitfalls_ja") or []),
            "".join(normalize_text((paper or {}).get("objective_ja")) for paper in papers),
            "".join(normalize_text((paper or {}).get("method_ja")) for paper in papers),
            "".join(normalize_text((paper or {}).get("finding_ja")) for paper in papers),
        ]
    )
    article_lower = article_text.lower()
    if (doc_id and doc_id.lower() in article_lower) or (equipment_id and equipment_id.lower() in article_lower):
        issues.append("internal_id_reference_hit")
    if INTERNAL_ID_PATTERN.search(article_text):
        issues.append("internal_id_reference_hit")

    if any(PLACEHOLDER_DOI_PATTERN.search(normalize_text((paper or {}).get("doi"))) for paper in papers):
        issues.append("placeholder_doi_hit")

    text_blocks_for_doi = [
        normalize_text(general.get("summary_ja")),
        normalize_text(beginner.get("principle_ja")),
        normalize_text(beginner.get("sample_guidance_ja")),
        "".join(normalize_text((paper or {}).get("objective_ja")) for paper in papers),
        "".join(normalize_text((paper or {}).get("method_ja")) for paper in papers),
        "".join(normalize_text((paper or {}).get("finding_ja")) for paper in papers),
    ]
    if any(DOI_TEXT_PATTERN.search(block or "") for block in text_blocks_for_doi):
        issues.append("body_contains_doi")

    papers_count = int(target_row.get("papers_count") or 0)
    if papers_count >= 2 and len(papers) < 2:
        issues.append("insufficient_paper_explanations_for_multi_papers")

    elapsed_sec: Optional[int] = None
    if int(args.min_elapsed_sec or 0) > 0:
        elapsed_sec = resolve_elapsed(load_timing_log(timing_log_path), doc_id, equipment_id)
        if elapsed_sec is None:
            issues.append("timing_log_not_found")
        elif elapsed_sec < int(args.min_elapsed_sec):
            issues.append("timing_elapsed_below_threshold")

    deduped_issues = sorted(set(normalize_text(issue) for issue in issues if normalize_text(issue)))
    status = "PASS" if not deduped_issues else "FAIL"
    beginner_chars = beginner_non_ws_chars(manual, str(args.char_count_mode))
    max_chars = max(0, int(args.max_beginner_chars or 0))
    if max_chars > 0 and beginner_chars > max_chars:
        deduped_issues.append("invalid_beginner_max_chars")
        deduped_issues = sorted(set(deduped_issues))
        status = "FAIL"

    report = {
        "status": status,
        "generated_at": utc_now_iso(),
        "doc_id": doc_id,
        "equipment_id": equipment_id,
        "name": normalize_text(item.get("name")),
        "beginner_non_ws_chars": beginner_chars,
        "elapsed_sec": elapsed_sec,
        "issues": deduped_issues,
    }
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
