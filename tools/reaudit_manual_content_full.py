#!/usr/bin/env python3
"""Full-dataset manual content reaudit for relevance and manual-writing quality."""

from __future__ import annotations

import argparse
import gzip
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from apply_manual_curation_batch import normalize_manual_content

DEFAULT_REVIEWER = "codex-manual"
DEFAULT_MIN_CHARS = 2000
DEFAULT_MAX_CHARS = 3000

INTERNAL_ID_PATTERN = re.compile(r"\b(?:doc_id|equipment_id|eqnet-\d+)\b", re.IGNORECASE)
PLACEHOLDER_DOI_PATTERN = re.compile(r"10\.0000/", re.IGNORECASE)
AUTO_TEMPLATE_MARKERS = [
    "同カテゴリの近縁機器",
    "補助キーワード",
    "比較観点1では",
    "補助タグは",
    "確認語は",
    "警告語",
    "記録補助語",
    "運用上の補助タグとして",
    "補助見出しにして記録",
]
GENERIC_PAPER_TITLE_PATTERN = re.compile(r"の運用最適化に関する関連研究\s*\d+$")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def load_snapshot(path: Path) -> Dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def count_non_ws(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def beginner_non_ws_chars(beginner: Dict[str, Any]) -> int:
    principle = normalize_text(beginner.get("principle_ja"))
    sample = normalize_text(beginner.get("sample_guidance_ja"))
    steps = beginner.get("basic_steps_ja") if isinstance(beginner.get("basic_steps_ja"), list) else []
    pitfalls = beginner.get("common_pitfalls_ja") if isinstance(beginner.get("common_pitfalls_ja"), list) else []
    merged = "".join([principle, sample, "".join(normalize_text(v) for v in steps), "".join(normalize_text(v) for v in pitfalls)])
    return count_non_ws(merged)


def contains_internal_id(text: str, doc_id: str, equipment_id: str) -> bool:
    lower = text.lower()
    if doc_id and doc_id.lower() in lower:
        return True
    if equipment_id and equipment_id.lower() in lower:
        return True
    return bool(INTERNAL_ID_PATTERN.search(text))


def collect_known_dois(item: Dict[str, Any]) -> set[str]:
    out = set()
    papers = item.get("papers") if isinstance(item.get("papers"), list) else []
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        doi = normalize_text(paper.get("doi"))
        doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE).lower()
        if doi:
            out.add(doi)
    return out


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reaudit all manual content")
    parser.add_argument("--snapshot", default="frontend/dist/equipment_snapshot.json.gz")
    parser.add_argument("--output", default="tools/manual_content_full_reaudit.json")
    parser.add_argument("--reviewer", default=DEFAULT_REVIEWER)
    parser.add_argument("--min-beginner-chars", type=int, default=DEFAULT_MIN_CHARS)
    parser.add_argument("--max-beginner-chars", type=int, default=DEFAULT_MAX_CHARS)
    parser.add_argument("--max-docs-per-issue", type=int, default=200)
    args = parser.parse_args()

    root = Path.cwd()
    snapshot_path = (root / args.snapshot).resolve()
    output_path = (root / args.output).resolve()

    payload = load_snapshot(snapshot_path)
    items = payload.get("items") if isinstance(payload.get("items"), list) else []

    issue_counts: Counter[str] = Counter()
    issue_docs: Dict[str, List[str]] = {}
    marker_counts: Counter[str] = Counter()
    chars: List[int] = []
    reviewed_status: Counter[str] = Counter()

    template_like_docs = 0
    manual_ok_docs = 0

    max_docs = max(1, int(args.max_docs_per_issue))
    reviewer = normalize_text(args.reviewer) or DEFAULT_REVIEWER
    min_chars = max(0, int(args.min_beginner_chars))
    max_chars = max(0, int(args.max_beginner_chars))

    def add_issue(code: str, doc_id: str) -> None:
        issue_counts[code] += 1
        bucket = issue_docs.setdefault(code, [])
        if len(bucket) < max_docs:
            bucket.append(doc_id)

    for item in items:
        if not isinstance(item, dict):
            continue
        doc_id = normalize_text(item.get("doc_id")) or normalize_text(item.get("equipment_id")) or "unknown"
        eq_id = normalize_text(item.get("equipment_id"))
        name = normalize_text(item.get("name"))

        manual = item.get("manual_content_v1") if isinstance(item.get("manual_content_v1"), dict) else {}
        review = manual.get("review") if isinstance(manual.get("review"), dict) else {}
        status = normalize_text(review.get("status")).lower() or "pending"
        reviewed_status[status] += 1

        general = manual.get("general_usage") if isinstance(manual.get("general_usage"), dict) else {}
        beginner = manual.get("beginner_guide") if isinstance(manual.get("beginner_guide"), dict) else {}
        papers = manual.get("paper_explanations") if isinstance(manual.get("paper_explanations"), list) else []

        known_dois = collect_known_dois(item)
        _, validation_issues = normalize_manual_content(
            manual,
            reviewer,
            known_dois,
            beginner_min_chars=min_chars,
            beginner_max_chars=max_chars,
            char_count_mode="non_whitespace",
            doc_id=doc_id,
            equipment_id=eq_id,
            equipment_name=name,
            forbid_internal_id=True,
            forbid_placeholder_doi=True,
        )
        for code in validation_issues:
            add_issue(code, doc_id)

        summary = normalize_text(general.get("summary_ja"))
        principle = normalize_text(beginner.get("principle_ja"))
        sample = normalize_text(beginner.get("sample_guidance_ja"))
        steps = beginner.get("basic_steps_ja") if isinstance(beginner.get("basic_steps_ja"), list) else []
        pitfalls = beginner.get("common_pitfalls_ja") if isinstance(beginner.get("common_pitfalls_ja"), list) else []
        paper_text = "".join(
            normalize_text((paper or {}).get("objective_ja"))
            + normalize_text((paper or {}).get("method_ja"))
            + normalize_text((paper or {}).get("finding_ja"))
            for paper in papers
            if isinstance(paper, dict)
        )
        article_text = "".join([summary, principle, sample, "".join(normalize_text(v) for v in steps), "".join(normalize_text(v) for v in pitfalls), paper_text])

        chars_value = beginner_non_ws_chars(beginner)
        chars.append(chars_value)
        if chars_value < min_chars:
            add_issue("beginner_min_chars_not_met", doc_id)
        if max_chars > 0 and chars_value > max_chars:
            add_issue("beginner_max_chars_exceeded", doc_id)

        if not name or name not in summary:
            add_issue("name_not_in_summary", doc_id)
        if not name or name not in principle:
            add_issue("name_not_in_principle", doc_id)

        if contains_internal_id(article_text, doc_id, eq_id):
            add_issue("internal_id_reference_hit", doc_id)
        if PLACEHOLDER_DOI_PATTERN.search(article_text):
            add_issue("placeholder_doi_hit", doc_id)

        has_template_marker = False
        for marker in AUTO_TEMPLATE_MARKERS:
            if marker in article_text:
                marker_counts[marker] += 1
                has_template_marker = True
        if has_template_marker:
            template_like_docs += 1
            add_issue("auto_template_marker_hit", doc_id)

        if papers:
            first_title = normalize_text((papers[0] or {}).get("title"))
            if first_title and GENERIC_PAPER_TITLE_PATTERN.search(first_title):
                add_issue("generic_paper_title_pattern", doc_id)

        if not validation_issues and not has_template_marker and chars_value >= min_chars and (max_chars == 0 or chars_value <= max_chars):
            manual_ok_docs += 1

    report = {
        "generated_at": utc_now_iso(),
        "snapshot_path": str(snapshot_path),
        "reviewer_expected": reviewer,
        "thresholds": {
            "min_beginner_chars": min_chars,
            "max_beginner_chars": max_chars,
        },
        "counts": {
            "total_items": len(items),
            "review_status": dict(reviewed_status),
            "manual_ok_docs": manual_ok_docs,
            "manual_ng_docs": len(items) - manual_ok_docs,
            "template_like_docs": template_like_docs,
            "beginner_char_min": min(chars) if chars else 0,
            "beginner_char_max": max(chars) if chars else 0,
            "beginner_char_avg": round(sum(chars) / float(len(chars)), 2) if chars else 0.0,
        },
        "issue_counts": dict(issue_counts),
        "issue_docs": issue_docs,
        "template_marker_counts": dict(marker_counts),
    }
    save_json(output_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
