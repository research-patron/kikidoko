#!/usr/bin/env python3
"""Strict authenticity audit for manual curation batches."""

from __future__ import annotations

import argparse
import difflib
import gzip
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from apply_manual_curation_batch import extract_known_dois, normalize_manual_content

DEFAULT_REVIEWER = "codex-manual"

FORBIDDEN_PATTERNS = [
    re.compile(r"この研究では.+を題材に", re.IGNORECASE),
    re.compile(r"手法としては試料調製条件を統一した後", re.IGNORECASE),
    re.compile(r"結果として.+有意な傾向", re.IGNORECASE),
    re.compile(r"対象から得られる信号を高感度に取得し", re.IGNORECASE),
    re.compile(r"標準試料で感度とバックグラウンドを点検し", re.IGNORECASE),
    re.compile(r"標準試料の再測定を省くとドリフトを見落とし", re.IGNORECASE),
]
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
INTERNAL_ID_PATTERN = re.compile(r"\beqnet-\d+\b", re.IGNORECASE)
PLACEHOLDER_DOI_PATTERN = re.compile(r"^10\.0000/", re.IGNORECASE)
DOI_TEXT_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def count_chars(text: Any, mode: str = "non_whitespace") -> int:
    raw = str(text or "")
    if mode == "non_whitespace":
        return len(re.sub(r"\s+", "", raw))
    return len(raw.strip())


def normalize_for_similarity(text: Any) -> str:
    value = str(text or "").lower()
    value = re.sub(r"\s+", "", value)
    value = re.sub(r"[、。,.!！?？:：;；'\"“”‘’\-\(\)\[\]{}<>/\\|]", "", value)
    return value


def load_snapshot(path: Path) -> Dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dedupe_rate(values: List[str]) -> float:
    if not values:
        return 0.0
    unique = len(set(values))
    return (len(values) - unique) / float(len(values))


def most_common_ratio(values: List[str]) -> float:
    cleaned = [v for v in values if normalize_text(v)]
    if not cleaned:
        return 0.0
    top_count = Counter(cleaned).most_common(1)[0][1]
    return top_count / float(len(cleaned))


def row_key(doc_id: str, equipment_id: str, index: int) -> str:
    if doc_id and equipment_id:
        return f"{doc_id}::{equipment_id}"
    if doc_id:
        return f"{doc_id}::"
    if equipment_id:
        return f"::{equipment_id}"
    return f"row-{index:06d}"


def index_snapshot_items(items: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    by_doc: Dict[str, Dict[str, Any]] = {}
    by_equipment: Dict[str, Dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        doc_id = normalize_text(item.get("doc_id"))
        equipment_id = normalize_text(item.get("equipment_id"))
        if doc_id and doc_id not in by_doc:
            by_doc[doc_id] = item
        if equipment_id and equipment_id not in by_equipment:
            by_equipment[equipment_id] = item
    return by_doc, by_equipment


def find_item(by_doc: Dict[str, Dict[str, Any]], by_equipment: Dict[str, Dict[str, Any]], doc_id: str, equipment_id: str) -> Dict[str, Any] | None:
    if doc_id and doc_id in by_doc:
        return by_doc[doc_id]
    if equipment_id and equipment_id in by_equipment:
        return by_equipment[equipment_id]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit manual authenticity for a curation batch")
    parser.add_argument("--snapshot", default="frontend/dist/equipment_snapshot.json.gz")
    parser.add_argument("--queue", default="tools/manual_curation_queue_next100.jsonl")
    parser.add_argument("--checkpoint", default="tools/manual_curation_checkpoint_next100.json")
    parser.add_argument("--session", required=True)
    parser.add_argument("--output", default="tools/manual_authenticity_audit_report.json")
    parser.add_argument("--reviewer", default=DEFAULT_REVIEWER)
    parser.add_argument("--min-beginner-chars", type=int, default=2000)
    parser.add_argument("--max-beginner-chars", type=int, default=3000)
    parser.add_argument(
        "--char-count-mode",
        default="non_whitespace",
        choices=["non_whitespace", "raw"],
    )
    parser.add_argument(
        "--step2-same-ratio-threshold",
        type=float,
        default=0.05,
        help="Maximum allowed most-common ratio for step2 text",
    )
    parser.add_argument(
        "--pitfall2-same-ratio-threshold",
        type=float,
        default=0.05,
        help="Maximum allowed most-common ratio for pitfall2 text",
    )
    parser.add_argument(
        "--min-reviewed-at-unique",
        type=int,
        default=90,
        help="Minimum unique reviewed_at values required in target rows",
    )
    parser.add_argument("--similarity-threshold", type=float, default=0.92)
    args = parser.parse_args()

    root = Path.cwd()
    snapshot_path = (root / args.snapshot).resolve()
    queue_path = (root / args.queue).resolve()
    checkpoint_path = (root / args.checkpoint).resolve()
    session_path = (root / args.session).resolve()
    output_path = (root / args.output).resolve()

    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")
    if not session_path.exists():
        raise FileNotFoundError(f"Session not found: {session_path}")

    session = load_json(session_path, {})
    if not isinstance(session, dict):
        raise ValueError(f"Invalid session: {session_path}")

    target_info = session.get("queue") if isinstance(session.get("queue"), dict) else {}
    target_rows = target_info.get("target_rows") if isinstance(target_info.get("target_rows"), list) else []
    if not target_rows:
        raise ValueError("Session does not have target_rows")

    snapshot = load_snapshot(snapshot_path)
    items = snapshot.get("items") if isinstance(snapshot.get("items"), list) else []
    by_doc, by_equipment = index_snapshot_items(items)

    reviewer_expected = normalize_text(args.reviewer) or DEFAULT_REVIEWER

    summary_values: List[str] = []
    principle_values: List[str] = []
    step1_values: List[str] = []
    pitfall1_values: List[str] = []
    step2_values: List[str] = []
    pitfall2_values: List[str] = []
    reviewed_at_values: List[str] = []
    beginner_char_values: List[int] = []
    guide_full_values: List[str] = []
    guide_similarity_values: List[str] = []

    issues: List[Dict[str, Any]] = []
    issue_counter: Counter[str] = Counter()
    row_key_to_doc_id: Dict[str, str] = {}
    forbidden_hits = 0
    internal_id_hits = 0
    placeholder_doi_hits = 0
    body_doi_hits = 0
    template_marker_hits = 0
    inspected_count = 0

    for idx, row in enumerate(target_rows):
        if not isinstance(row, dict):
            continue
        doc_id = normalize_text(row.get("doc_id"))
        equipment_id = normalize_text(row.get("equipment_id"))
        key = normalize_text(row.get("row_key")) or row_key(doc_id, equipment_id, idx)
        row_key_to_doc_id[key] = doc_id or equipment_id or key
        papers_count = int(row.get("papers_count") or 0)

        item = find_item(by_doc, by_equipment, doc_id, equipment_id)
        if not item:
            issues.append({"row_key": key, "code": "target_item_not_found", "doc_id": doc_id, "equipment_id": equipment_id})
            issue_counter["target_item_not_found"] += 1
            continue
        equipment_name = normalize_text(item.get("name"))

        inspected_count += 1
        manual = item.get("manual_content_v1") if isinstance(item.get("manual_content_v1"), dict) else {}
        review = manual.get("review") if isinstance(manual.get("review"), dict) else {}
        reviewer = normalize_text(review.get("reviewer"))
        reviewed_at = normalize_text(review.get("reviewed_at"))
        reviewed_at_values.append(reviewed_at)
        if reviewer != reviewer_expected:
            issues.append({"row_key": key, "code": "reviewer_mismatch", "reviewer": reviewer})
            issue_counter["reviewer_mismatch"] += 1

        known_dois = extract_known_dois(item)
        _, content_issues = normalize_manual_content(
            manual,
            reviewer_expected,
            known_dois,
            beginner_min_chars=max(0, int(args.min_beginner_chars)),
            beginner_max_chars=max(0, int(args.max_beginner_chars)),
            char_count_mode=str(args.char_count_mode or "non_whitespace"),
            doc_id=doc_id,
            equipment_id=equipment_id,
            equipment_name=equipment_name,
            forbid_internal_id=True,
            forbid_placeholder_doi=True,
        )
        for code in content_issues:
            issues.append({"row_key": key, "code": code})
            issue_counter[code] += 1

        general = manual.get("general_usage") if isinstance(manual.get("general_usage"), dict) else {}
        beginner = manual.get("beginner_guide") if isinstance(manual.get("beginner_guide"), dict) else {}
        papers = manual.get("paper_explanations") if isinstance(manual.get("paper_explanations"), list) else []

        summary = normalize_text(general.get("summary_ja"))
        principle = normalize_text(beginner.get("principle_ja"))
        basic_steps = beginner.get("basic_steps_ja") if isinstance(beginner.get("basic_steps_ja"), list) else []
        pitfalls = beginner.get("common_pitfalls_ja") if isinstance(beginner.get("common_pitfalls_ja"), list) else []

        summary_values.append(summary)
        principle_values.append(principle)
        step1_values.append(normalize_text(basic_steps[0] if basic_steps else ""))
        pitfall1_values.append(normalize_text(pitfalls[0] if pitfalls else ""))
        step2_values.append(normalize_text(basic_steps[1] if len(basic_steps) > 1 else ""))
        pitfall2_values.append(normalize_text(pitfalls[1] if len(pitfalls) > 1 else ""))
        guide_full = "".join(
            [
                summary,
                principle,
                normalize_text(beginner.get("sample_guidance_ja")),
                "".join(normalize_text(v) for v in basic_steps),
                "".join(normalize_text(v) for v in pitfalls),
            ]
        )
        guide_full_values.append(guide_full)
        guide_similarity_values.append(normalize_for_similarity(guide_full))

        article_text = "".join(
            [
                summary,
                principle,
                normalize_text(beginner.get("sample_guidance_ja")),
                "".join(normalize_text(v) for v in basic_steps),
                "".join(normalize_text(v) for v in pitfalls),
                "".join(normalize_text((paper or {}).get("objective_ja")) for paper in papers),
                "".join(normalize_text((paper or {}).get("method_ja")) for paper in papers),
                "".join(normalize_text((paper or {}).get("finding_ja")) for paper in papers),
            ]
        )
        doc_id_lower = doc_id.lower()
        equipment_id_lower = equipment_id.lower()
        article_lower = article_text.lower()
        if (doc_id_lower and doc_id_lower in article_lower) or (
            equipment_id_lower and equipment_id_lower in article_lower
        ) or INTERNAL_ID_PATTERN.search(article_text):
            internal_id_hits += 1
            issues.append({"row_key": key, "code": "internal_id_reference_hit"})
            issue_counter["internal_id_reference_hit"] += 1
        if equipment_name and equipment_name not in summary:
            issues.append({"row_key": key, "code": "name_not_in_summary"})
            issue_counter["name_not_in_summary"] += 1
        if equipment_name and equipment_name not in principle:
            issues.append({"row_key": key, "code": "name_not_in_principle"})
            issue_counter["name_not_in_principle"] += 1
        if any(marker in article_text for marker in AUTO_TEMPLATE_MARKERS):
            template_marker_hits += 1
            issues.append({"row_key": key, "code": "auto_template_marker_hit"})
            issue_counter["auto_template_marker_hit"] += 1

        body_segments = [
            summary,
            principle,
            normalize_text(beginner.get("sample_guidance_ja")),
            "".join(normalize_text((paper or {}).get("objective_ja")) for paper in papers),
            "".join(normalize_text((paper or {}).get("method_ja")) for paper in papers),
            "".join(normalize_text((paper or {}).get("finding_ja")) for paper in papers),
        ]
        if any(DOI_TEXT_PATTERN.search(segment or "") for segment in body_segments):
            body_doi_hits += 1
            issues.append({"row_key": key, "code": "body_contains_doi"})
            issue_counter["body_contains_doi"] += 1

        beginner_chars = count_chars(
            "".join(
                [
                    principle,
                    normalize_text(beginner.get("sample_guidance_ja")),
                    "".join(normalize_text(v) for v in basic_steps),
                    "".join(normalize_text(v) for v in pitfalls),
                ]
            ),
            str(args.char_count_mode or "non_whitespace"),
        )
        beginner_char_values.append(beginner_chars)
        min_chars = max(0, int(args.min_beginner_chars))
        if min_chars > 0 and beginner_chars < min_chars:
            issues.append(
                {
                    "row_key": key,
                    "code": "beginner_min_chars_not_met",
                    "beginner_chars": beginner_chars,
                    "min_required": min_chars,
                }
            )
            issue_counter["beginner_min_chars_not_met"] += 1
        max_chars = max(0, int(args.max_beginner_chars))
        if max_chars > 0 and beginner_chars > max_chars:
            issues.append(
                {
                    "row_key": key,
                    "code": "beginner_max_chars_exceeded",
                    "beginner_chars": beginner_chars,
                    "max_allowed": max_chars,
                }
            )
            issue_counter["beginner_max_chars_exceeded"] += 1

        if papers_count >= 2 and len(papers) < 2:
            issues.append(
                {
                    "row_key": key,
                    "code": "insufficient_paper_explanations_for_multi_papers",
                    "papers_count": papers_count,
                    "paper_explanations_count": len(papers),
                }
            )
            issue_counter["insufficient_paper_explanations_for_multi_papers"] += 1

        for paper in papers:
            if not isinstance(paper, dict):
                continue
            doi = normalize_text(paper.get("doi"))
            if doi and PLACEHOLDER_DOI_PATTERN.search(doi):
                placeholder_doi_hits += 1
                issues.append({"row_key": key, "code": "placeholder_doi_hit", "doi": doi})
                issue_counter["placeholder_doi_hit"] += 1
                break

        check_texts = [summary, principle] + [normalize_text(v) for v in basic_steps] + [normalize_text(v) for v in pitfalls]
        for text in check_texts:
            if not text:
                continue
            if any(pattern.search(text) for pattern in FORBIDDEN_PATTERNS):
                forbidden_hits += 1
                issues.append({"row_key": key, "code": "forbidden_pattern_hit"})
                issue_counter["forbidden_pattern_hit"] += 1
                break

    summary_dup_rate = dedupe_rate([v for v in summary_values if v])
    principle_dup_rate = dedupe_rate([v for v in principle_values if v])
    step1_dup_rate = dedupe_rate([v for v in step1_values if v])
    pitfall1_dup_rate = dedupe_rate([v for v in pitfall1_values if v])
    step2_same_ratio = most_common_ratio(step2_values)
    pitfall2_same_ratio = most_common_ratio(pitfall2_values)
    reviewed_at_unique = len({v for v in reviewed_at_values if v})
    guide_full_dup_rate = dedupe_rate([v for v in guide_full_values if normalize_text(v)])
    near_duplicate_pairs: List[Dict[str, Any]] = []
    similarity_threshold = float(args.similarity_threshold)
    for i in range(len(guide_similarity_values)):
        left = guide_similarity_values[i]
        if not left:
            continue
        for j in range(i + 1, len(guide_similarity_values)):
            right = guide_similarity_values[j]
            if not right:
                continue
            ratio = difflib.SequenceMatcher(None, left, right).ratio()
            if ratio >= similarity_threshold:
                near_duplicate_pairs.append({"i": i, "j": j, "ratio": ratio})
                if len(near_duplicate_pairs) >= 50:
                    break
        if len(near_duplicate_pairs) >= 50:
            break

    threshold_failures: List[str] = []
    if summary_dup_rate != 0.0:
        threshold_failures.append("summary_dup_rate_not_zero")
    if principle_dup_rate != 0.0:
        threshold_failures.append("principle_dup_rate_not_zero")
    if step1_dup_rate != 0.0:
        threshold_failures.append("step1_dup_rate_not_zero")
    if pitfall1_dup_rate != 0.0:
        threshold_failures.append("pitfall1_dup_rate_not_zero")
    step2_threshold = max(0.0, float(args.step2_same_ratio_threshold))
    pitfall2_threshold = max(0.0, float(args.pitfall2_same_ratio_threshold))
    min_reviewed_at_unique = max(0, int(args.min_reviewed_at_unique))
    if step2_same_ratio > step2_threshold:
        threshold_failures.append("step2_same_ratio_gt_0_05")
    if pitfall2_same_ratio > pitfall2_threshold:
        threshold_failures.append("pitfall2_same_ratio_gt_0_05")
    if reviewed_at_unique < min_reviewed_at_unique:
        threshold_failures.append("reviewed_at_unique_lt_90")
    if forbidden_hits > 0:
        threshold_failures.append("forbidden_pattern_hit")
    if guide_full_dup_rate != 0.0:
        threshold_failures.append("guide_full_dup_rate_not_zero")
    if near_duplicate_pairs:
        threshold_failures.append("guide_high_similarity_detected")
    if internal_id_hits > 0:
        threshold_failures.append("internal_id_reference_hit")
    if placeholder_doi_hits > 0:
        threshold_failures.append("placeholder_doi_hit")
    if body_doi_hits > 0:
        threshold_failures.append("body_contains_doi")
    if template_marker_hits > 0:
        threshold_failures.append("auto_template_marker_hit")

    for code in threshold_failures:
        issue_counter[code] += 1

    checkpoint = load_json(checkpoint_path, {})
    result_status = "PASS" if (not issues and not threshold_failures) else "FAIL"
    offending_doc_ids = sorted(
        {row_key_to_doc_id.get(normalize_text(issue.get("row_key")), "") for issue in issues if row_key_to_doc_id.get(normalize_text(issue.get("row_key")), "")}
    )

    report = {
        "status": result_status,
        "generated_at": utc_now_iso(),
        "batch_id": normalize_text(session.get("batch_id")),
        "reviewer_expected": reviewer_expected,
        "snapshot_path": str(snapshot_path),
        "queue_path": str(queue_path),
        "checkpoint_path": str(checkpoint_path),
        "session_path": str(session_path),
        "inspected_count": inspected_count,
        "target_count": int(target_info.get("target_count") or 0),
        "metrics": {
            "summary_dup_rate": summary_dup_rate,
            "principle_dup_rate": principle_dup_rate,
            "step1_dup_rate": step1_dup_rate,
            "pitfall1_dup_rate": pitfall1_dup_rate,
            "step2_same_ratio": step2_same_ratio,
            "pitfall2_same_ratio": pitfall2_same_ratio,
            "reviewed_at_unique_count": reviewed_at_unique,
            "forbidden_pattern_hits": forbidden_hits,
            "internal_id_reference_hits": internal_id_hits,
            "placeholder_doi_hits": placeholder_doi_hits,
            "body_contains_doi_hits": body_doi_hits,
            "auto_template_marker_hits": template_marker_hits,
            "beginner_char_min": min(beginner_char_values) if beginner_char_values else 0,
            "beginner_char_max": max(beginner_char_values) if beginner_char_values else 0,
            "beginner_char_avg": (
                sum(beginner_char_values) / float(len(beginner_char_values)) if beginner_char_values else 0.0
            ),
            "guide_full_dup_rate": guide_full_dup_rate,
            "guide_high_similarity_pairs": len(near_duplicate_pairs),
            "step2_same_ratio_threshold": step2_threshold,
            "pitfall2_same_ratio_threshold": pitfall2_threshold,
            "min_reviewed_at_unique": min_reviewed_at_unique,
        },
        "threshold_failures": threshold_failures,
        "offending_doc_ids": offending_doc_ids,
        "issue_counts": dict(issue_counter),
        "issues": issues[:400],
        "near_duplicate_pairs": near_duplicate_pairs,
        "checkpoint_snapshot": checkpoint if isinstance(checkpoint, dict) else {},
    }
    save_json(output_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if result_status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
