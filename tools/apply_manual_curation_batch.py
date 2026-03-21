#!/usr/bin/env python3
"""Apply manually curated manual_content_v1 to equipment snapshot (fail-closed)."""

from __future__ import annotations

import argparse
import gzip
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

DEFAULT_REVIEWER = "codex-manual"
ALLOWED_REVIEW_STATUS = {"approved", "pending", "rejected"}
ALLOWED_SAMPLE_STATES = {"固体", "液体", "粉末", "気体", "生体", "その他"}
INTERNAL_ID_PATTERN = re.compile(r"\b(?:doc_id|equipment_id|eqnet-\d+)\b", re.IGNORECASE)
PLACEHOLDER_DOI_PATTERN = re.compile(r"^10\.0000/", re.IGNORECASE)
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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def has_japanese(text: Any) -> bool:
    return bool(re.search(r"[ぁ-んァ-ン一-龠々ー]", str(text or "")))


def normalize_doi(value: Any) -> str:
    doi = normalize_text(value)
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    return doi.lower()


def is_http_url(value: str) -> bool:
    if not value:
        return False
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def normalize_iso_datetime(value: Any) -> str:
    raw = normalize_text(value)
    if not raw:
        return ""
    candidate = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(candidate)
    except Exception:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def normalize_string_list(values: Any, max_items: int) -> List[str]:
    if not isinstance(values, list):
        return []
    out: List[str] = []
    for value in values:
        text = normalize_text(value)
        if text and text not in out:
            out.append(text)
    return out[:max_items]


def contains_internal_identifier(text: str, doc_id: str, equipment_id: str) -> bool:
    raw = normalize_text(text)
    if not raw:
        return False
    lower = raw.lower()
    doc = normalize_text(doc_id).lower()
    equipment = normalize_text(equipment_id).lower()
    if doc and doc in lower:
        return True
    if equipment and equipment in lower:
        return True
    return bool(INTERNAL_ID_PATTERN.search(raw))


def count_chars(text: Any, mode: str = "non_whitespace") -> int:
    raw = str(text or "")
    if mode == "non_whitespace":
        return len(re.sub(r"\s+", "", raw))
    return len(raw.strip())


def beginner_char_count(
    principle_ja: str,
    sample_guidance_ja: str,
    basic_steps: List[str],
    pitfalls: List[str],
    mode: str = "non_whitespace",
) -> int:
    text = "".join(
        [
            principle_ja,
            sample_guidance_ja,
            "".join(normalize_text(v) for v in basic_steps if normalize_text(v)),
            "".join(normalize_text(v) for v in pitfalls if normalize_text(v)),
        ]
    )
    return count_chars(text, mode)


def has_auto_template_marker(text: str) -> bool:
    raw = normalize_text(text)
    if not raw:
        return False
    for marker in AUTO_TEMPLATE_MARKERS:
        if marker in raw:
            return True
    return False


def default_manual_content(reviewer: str = DEFAULT_REVIEWER) -> Dict[str, Any]:
    return {
        "review": {
            "status": "pending",
            "reviewer": normalize_text(reviewer) or DEFAULT_REVIEWER,
            "reviewed_at": "",
        },
        "general_usage": {
            "summary_ja": "",
            "sample_states": [],
            "research_fields_ja": [],
        },
        "paper_explanations": [],
        "beginner_guide": {
            "principle_ja": "",
            "sample_guidance_ja": "",
            "basic_steps_ja": [],
            "common_pitfalls_ja": [],
        },
    }


def load_snapshot(path: Path) -> Dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def save_snapshot(path: Path, payload: Dict[str, Any]) -> None:
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))


def load_queue(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def save_queue(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


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


def load_timing_log(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
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


def resolve_elapsed_from_log(
    timing_rows: List[Dict[str, Any]],
    doc_id: str,
    equipment_id: str,
) -> Optional[int]:
    doc_id = normalize_text(doc_id)
    equipment_id = normalize_text(equipment_id)
    for row in reversed(timing_rows):
        if normalize_text(row.get("doc_id")) != doc_id:
            continue
        if equipment_id and normalize_text(row.get("equipment_id")) not in {"", equipment_id}:
            continue
        try:
            elapsed = int(row.get("elapsed_sec"))
        except Exception:
            return None
        return elapsed
    return None


def build_index(items: List[Dict[str, Any]]) -> Tuple[Dict[str, List[int]], Dict[str, int]]:
    by_equipment_id: Dict[str, List[int]] = {}
    by_doc_id: Dict[str, int] = {}
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        eq_id = normalize_text(item.get("equipment_id"))
        doc_id = normalize_text(item.get("doc_id"))
        if eq_id:
            by_equipment_id.setdefault(eq_id, []).append(idx)
        if doc_id and doc_id not in by_doc_id:
            by_doc_id[doc_id] = idx
    return by_equipment_id, by_doc_id


def resolve_target_index(row: Dict[str, Any], by_equipment_id: Dict[str, List[int]], by_doc_id: Dict[str, int]) -> int:
    doc_id = normalize_text(row.get("doc_id"))
    if doc_id and doc_id in by_doc_id:
        return by_doc_id[doc_id]
    equipment_id = normalize_text(row.get("equipment_id"))
    if equipment_id:
        candidates = by_equipment_id.get(equipment_id) or []
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            return -2
    return -1


def extract_known_dois(item: Dict[str, Any]) -> Set[str]:
    papers = item.get("papers") if isinstance(item.get("papers"), list) else []
    out: Set[str] = set()
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        doi = normalize_doi(paper.get("doi"))
        if doi:
            out.add(doi)
    return out


def queue_row_key(row: Dict[str, Any], index: int) -> str:
    doc_id = normalize_text(row.get("doc_id"))
    equipment_id = normalize_text(row.get("equipment_id"))
    if doc_id and equipment_id:
        return f"{doc_id}::{equipment_id}"
    if doc_id:
        return f"{doc_id}::"
    if equipment_id:
        return f"::{equipment_id}"
    return f"row-{index:06d}"


def normalize_manual_content(
    payload: Any,
    reviewer_default: str,
    known_dois: Set[str],
    beginner_min_chars: int = 0,
    beginner_max_chars: int = 0,
    char_count_mode: str = "non_whitespace",
    doc_id: str = "",
    equipment_id: str = "",
    equipment_name: str = "",
    forbid_internal_id: bool = True,
    forbid_placeholder_doi: bool = True,
) -> Tuple[Dict[str, Any], List[str]]:
    issues: List[str] = []
    source = payload if isinstance(payload, dict) else {}

    review = source.get("review") if isinstance(source.get("review"), dict) else {}
    review_status = normalize_text(review.get("status")).lower() or "pending"
    if review_status not in ALLOWED_REVIEW_STATUS:
        issues.append("invalid_review_status")
        review_status = "pending"

    reviewer_expected = normalize_text(reviewer_default) or DEFAULT_REVIEWER
    reviewer = normalize_text(review.get("reviewer")) or reviewer_expected

    raw_reviewed_at = normalize_text(review.get("reviewed_at"))
    reviewed_at = normalize_iso_datetime(raw_reviewed_at)

    general = source.get("general_usage") if isinstance(source.get("general_usage"), dict) else {}
    summary_ja = normalize_text(general.get("summary_ja"))
    sample_states = normalize_string_list(general.get("sample_states"), max_items=6)
    research_fields = normalize_string_list(general.get("research_fields_ja"), max_items=4)

    papers = source.get("paper_explanations") if isinstance(source.get("paper_explanations"), list) else []
    normalized_papers: List[Dict[str, str]] = []
    for paper in papers[:3]:
        if not isinstance(paper, dict):
            continue
        doi = normalize_doi(paper.get("doi"))
        title = normalize_text(paper.get("title"))
        objective_ja = normalize_text(paper.get("objective_ja"))
        method_ja = normalize_text(paper.get("method_ja"))
        finding_ja = normalize_text(paper.get("finding_ja"))
        link_url = normalize_text(paper.get("link_url"))

        if doi and not link_url:
            link_url = f"https://doi.org/{doi}"

        normalized_papers.append(
            {
                "doi": doi,
                "title": title,
                "objective_ja": objective_ja,
                "method_ja": method_ja,
                "finding_ja": finding_ja,
                "link_url": link_url,
            }
        )

    beginner = source.get("beginner_guide") if isinstance(source.get("beginner_guide"), dict) else {}
    principle_ja = normalize_text(beginner.get("principle_ja"))
    sample_guidance_ja = normalize_text(beginner.get("sample_guidance_ja"))
    basic_steps = normalize_string_list(beginner.get("basic_steps_ja") or beginner.get("basic_steps"), max_items=6)
    pitfalls = normalize_string_list(
        beginner.get("common_pitfalls_ja") or beginner.get("common_pitfalls"), max_items=6
    )

    if review_status in {"approved", "rejected"}:
        if reviewer != reviewer_expected:
            issues.append("invalid_reviewer")
        if not reviewed_at:
            issues.append("invalid_reviewed_at")

    if review_status == "approved":
        if len(summary_ja) < 40 or not has_japanese(summary_ja):
            issues.append("invalid_general_summary")
        if equipment_name and equipment_name not in summary_ja:
            issues.append("name_not_in_summary")

        if not (1 <= len(sample_states) <= 6):
            issues.append("invalid_sample_states_count")
        else:
            if any(state not in ALLOWED_SAMPLE_STATES for state in sample_states):
                issues.append("invalid_sample_states_value")

        if not (1 <= len(research_fields) <= 4):
            issues.append("invalid_research_fields_count")
        else:
            if any(not has_japanese(field) for field in research_fields):
                issues.append("invalid_research_fields_language")

        if not (1 <= len(normalized_papers) <= 3):
            issues.append("invalid_paper_explanations_count")
        for entry in normalized_papers:
            doi = entry["doi"]
            title = entry["title"]
            objective_ja = entry["objective_ja"]
            method_ja = entry["method_ja"]
            finding_ja = entry["finding_ja"]
            link_url = entry["link_url"]

            if not doi:
                issues.append("missing_paper_doi")
            if known_dois and doi and doi not in known_dois:
                issues.append("paper_doi_not_found_in_item")
            if len(title) < 4:
                issues.append("invalid_paper_title")
            if len(objective_ja) < 20 or not has_japanese(objective_ja):
                issues.append("invalid_paper_objective")
            if len(method_ja) < 20 or not has_japanese(method_ja):
                issues.append("invalid_paper_method")
            if len(finding_ja) < 20 or not has_japanese(finding_ja):
                issues.append("invalid_paper_finding")
            if not is_http_url(link_url):
                issues.append("invalid_paper_link_url")
            if doi and "doi.org/" in link_url.lower():
                link_doi = normalize_doi(link_url)
                if link_doi != doi:
                    issues.append("doi_link_mismatch")
            if forbid_placeholder_doi and doi and PLACEHOLDER_DOI_PATTERN.search(doi):
                issues.append("placeholder_doi_hit")
            if forbid_placeholder_doi:
                link_doi = normalize_doi(link_url)
                if link_doi and PLACEHOLDER_DOI_PATTERN.search(link_doi):
                    issues.append("placeholder_doi_hit")

        if len(principle_ja) < 30 or not has_japanese(principle_ja):
            issues.append("invalid_beginner_principle")
        if equipment_name and equipment_name not in principle_ja:
            issues.append("name_not_in_principle")
        if len(sample_guidance_ja) < 20 or not has_japanese(sample_guidance_ja):
            issues.append("invalid_beginner_sample_guidance")

        if not (3 <= len(basic_steps) <= 6):
            issues.append("invalid_beginner_basic_steps_count")
        else:
            if any(len(step) < 8 or not has_japanese(step) for step in basic_steps):
                issues.append("invalid_beginner_basic_steps_value")

        if not (2 <= len(pitfalls) <= 6):
            issues.append("invalid_beginner_pitfalls_count")
        else:
            if any(len(step) < 8 or not has_japanese(step) for step in pitfalls):
                issues.append("invalid_beginner_pitfalls_value")

        min_chars = max(0, int(beginner_min_chars or 0))
        max_chars = max(0, int(beginner_max_chars or 0))
        actual_chars = 0
        if min_chars > 0 or max_chars > 0:
            actual_chars = beginner_char_count(principle_ja, sample_guidance_ja, basic_steps, pitfalls, char_count_mode)
        if min_chars > 0:
            if actual_chars < min_chars:
                issues.append("invalid_beginner_min_chars")
        if max_chars > 0:
            if actual_chars > max_chars:
                issues.append("invalid_beginner_max_chars")

        if forbid_internal_id:
            article_text = "".join(
                [
                    summary_ja,
                    "".join(research_fields),
                    principle_ja,
                    sample_guidance_ja,
                    "".join(basic_steps),
                    "".join(pitfalls),
                    "".join(entry["objective_ja"] for entry in normalized_papers),
                    "".join(entry["method_ja"] for entry in normalized_papers),
                    "".join(entry["finding_ja"] for entry in normalized_papers),
                ]
            )
            if contains_internal_identifier(article_text, doc_id, equipment_id):
                issues.append("internal_id_reference_hit")
            if has_auto_template_marker(article_text):
                issues.append("auto_template_marker_hit")

    normalized = {
        "review": {
            "status": review_status,
            "reviewer": reviewer,
            "reviewed_at": reviewed_at,
        },
        "general_usage": {
            "summary_ja": summary_ja,
            "sample_states": sample_states,
            "research_fields_ja": research_fields,
        },
        "paper_explanations": normalized_papers,
        "beginner_guide": {
            "principle_ja": principle_ja,
            "sample_guidance_ja": sample_guidance_ja,
            "basic_steps_ja": basic_steps,
            "common_pitfalls_ja": pitfalls,
        },
    }
    return normalized, sorted(set(issues))


def row_payload(row: Dict[str, Any], reviewer_default: str) -> Dict[str, Any]:
    payload = row.get("manual_content_v1") if isinstance(row.get("manual_content_v1"), dict) else {}
    if payload:
        return payload

    return {
        "review": {
            "status": normalize_text(row.get("review_status")) or "pending",
            "reviewer": normalize_text(row.get("reviewer")) or reviewer_default,
            "reviewed_at": normalize_text(row.get("reviewed_at")),
        },
        "general_usage": {
            "summary_ja": normalize_text(row.get("summary_ja")),
            "sample_states": row.get("sample_states") if isinstance(row.get("sample_states"), list) else [],
            "research_fields_ja": row.get("research_fields_ja") if isinstance(row.get("research_fields_ja"), list) else [],
        },
        "paper_explanations": row.get("paper_explanations") if isinstance(row.get("paper_explanations"), list) else [],
        "beginner_guide": {
            "principle_ja": normalize_text(row.get("principle_ja")),
            "sample_guidance_ja": normalize_text(row.get("sample_guidance_ja")),
            "basic_steps_ja": (
                row.get("basic_steps_ja")
                if isinstance(row.get("basic_steps_ja"), list)
                else row.get("basic_steps")
                if isinstance(row.get("basic_steps"), list)
                else []
            ),
            "common_pitfalls_ja": (
                row.get("common_pitfalls_ja")
                if isinstance(row.get("common_pitfalls_ja"), list)
                else row.get("common_pitfalls")
                if isinstance(row.get("common_pitfalls"), list)
                else []
            ),
        },
    }


def mark_needs_manual_fix(row: Dict[str, Any], codes: List[str]) -> None:
    existing = row.get("issue_flags") if isinstance(row.get("issue_flags"), list) else []
    merged = sorted({normalize_text(code) for code in existing + codes if normalize_text(code)})
    row["status"] = "needs_manual_fix"
    row["issue_flags"] = merged
    row["updated_at"] = utc_now_iso()


def run_guard_verify(
    root: Path,
    attestation_path: Path,
    queue_path: Path,
    snapshot_path: Path,
    agents_path: Path,
    reviewer: str,
) -> Tuple[bool, Dict[str, Any], str]:
    guard_script = (root / "tools/manual_guard.py").resolve()
    if not guard_script.exists():
        return False, {}, f"manual_guard.py not found: {guard_script}"

    cmd = [
        sys.executable,
        str(guard_script),
        "verify",
        "--session",
        str(attestation_path),
        "--queue",
        str(queue_path),
        "--snapshot",
        str(snapshot_path),
        "--agents",
        str(agents_path),
        "--reviewer",
        reviewer,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    merged_output = "\n".join([part for part in [result.stdout.strip(), result.stderr.strip()] if part])
    parsed: Dict[str, Any] = {}
    try:
        parsed = json.loads(result.stdout) if result.stdout.strip() else {}
    except Exception:
        parsed = {}
    return result.returncode == 0, parsed, merged_output


def run_post_audit(
    root: Path,
    audit_script_path: Path,
    snapshot_path: Path,
    queue_path: Path,
    checkpoint_path: Path,
    session_path: Path,
    output_path: Path,
    reviewer: str,
    beginner_min_chars: int,
    beginner_max_chars: int,
    char_count_mode: str,
    step2_same_ratio_threshold: float,
    pitfall2_same_ratio_threshold: float,
    min_reviewed_at_unique: int,
    similarity_threshold: float,
) -> Tuple[bool, Dict[str, Any], str]:
    if not audit_script_path.exists():
        return False, {}, f"audit script not found: {audit_script_path}"

    cmd = [
        sys.executable,
        str(audit_script_path),
        "--snapshot",
        str(snapshot_path),
        "--queue",
        str(queue_path),
        "--checkpoint",
        str(checkpoint_path),
        "--session",
        str(session_path),
        "--output",
        str(output_path),
        "--reviewer",
        reviewer,
        "--min-beginner-chars",
        str(max(0, int(beginner_min_chars or 0))),
        "--max-beginner-chars",
        str(max(0, int(beginner_max_chars or 0))),
        "--char-count-mode",
        str(char_count_mode or "non_whitespace"),
        "--step2-same-ratio-threshold",
        str(float(step2_same_ratio_threshold)),
        "--pitfall2-same-ratio-threshold",
        str(float(pitfall2_same_ratio_threshold)),
        "--min-reviewed-at-unique",
        str(max(0, int(min_reviewed_at_unique))),
        "--similarity-threshold",
        str(float(similarity_threshold)),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    report = load_json(output_path, {})
    status = normalize_text(report.get("status")).upper() if isinstance(report, dict) else ""
    merged_output = "\n".join([part for part in [result.stdout.strip(), result.stderr.strip()] if part])
    ok = result.returncode == 0 and status == "PASS"
    return ok, report if isinstance(report, dict) else {}, merged_output


def finalize_queue_rows(pairs: List[Tuple[int, Dict[str, Any]]]) -> List[Dict[str, Any]]:
    pairs.sort(key=lambda p: p[0])
    return [row for _, row in pairs]


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply manual curation batch")
    parser.add_argument("--snapshot", default="frontend/dist/equipment_snapshot.json.gz")
    parser.add_argument("--queue", default="tools/manual_curation_queue.jsonl")
    parser.add_argument("--checkpoint", default="tools/manual_curation_checkpoint.json")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--process-all", action="store_true")
    parser.add_argument("--reviewer-default", default=DEFAULT_REVIEWER)
    parser.add_argument("--attestation", required=True, help="Path to manual_guard session json")
    parser.add_argument("--agents", default="AGENTS.md")
    parser.add_argument("--post-audit-script", default="tools/audit_manual_authenticity.py")
    parser.add_argument("--post-audit-output", default="tools/manual_authenticity_audit_report.json")
    parser.add_argument("--enforce-beginner-min-chars", type=int, default=2000)
    parser.add_argument("--enforce-beginner-max-chars", type=int, default=3000)
    parser.add_argument(
        "--char-count-mode",
        default="non_whitespace",
        choices=["non_whitespace", "raw"],
    )
    parser.add_argument(
        "--post-audit-step2-same-ratio-threshold",
        type=float,
        default=0.05,
    )
    parser.add_argument(
        "--post-audit-pitfall2-same-ratio-threshold",
        type=float,
        default=0.05,
    )
    parser.add_argument(
        "--post-audit-min-reviewed-at-unique",
        type=int,
        default=90,
    )
    parser.add_argument(
        "--post-audit-similarity-threshold",
        type=float,
        default=0.92,
    )
    parser.add_argument(
        "--forbid-internal-id",
        dest="forbid_internal_id",
        action="store_true",
        default=True,
        help="Reject content containing internal IDs in article body.",
    )
    parser.add_argument(
        "--allow-internal-id",
        dest="forbid_internal_id",
        action="store_false",
        help="Disable internal ID rejection (not recommended).",
    )
    parser.add_argument(
        "--forbid-placeholder-doi",
        dest="forbid_placeholder_doi",
        action="store_true",
        default=True,
        help="Reject placeholder DOI values (10.0000/*).",
    )
    parser.add_argument(
        "--allow-placeholder-doi",
        dest="forbid_placeholder_doi",
        action="store_false",
        help="Disable placeholder DOI rejection (not recommended).",
    )
    parser.add_argument(
        "--timing-log",
        default="tools/manual_item_timing_log.jsonl",
        help="Per-item timing log JSONL path.",
    )
    parser.add_argument(
        "--enforce-min-elapsed-sec",
        type=int,
        default=0,
        help="Reject rows when latest timing elapsed_sec is below this threshold (0 disables).",
    )
    args = parser.parse_args()

    root = Path.cwd()
    snapshot_path = (root / args.snapshot).resolve()
    queue_path = (root / args.queue).resolve()
    checkpoint_path = (root / args.checkpoint).resolve()
    attestation_path = (root / args.attestation).resolve()
    agents_path = (root / args.agents).resolve()
    post_audit_script = (root / args.post_audit_script).resolve()
    post_audit_output = (root / args.post_audit_output).resolve()
    timing_log_path = (root / args.timing_log).resolve()

    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")
    if not queue_path.exists():
        raise FileNotFoundError(f"Queue not found: {queue_path}")
    if not attestation_path.exists():
        raise FileNotFoundError(f"Attestation not found: {attestation_path}")
    if not agents_path.exists():
        raise FileNotFoundError(f"AGENTS not found: {agents_path}")

    reviewer_default = normalize_text(args.reviewer_default) or DEFAULT_REVIEWER
    beginner_min_chars = max(0, int(args.enforce_beginner_min_chars))
    beginner_max_chars = max(0, int(args.enforce_beginner_max_chars))
    char_count_mode = str(args.char_count_mode or "non_whitespace")
    forbid_internal_id = bool(args.forbid_internal_id)
    forbid_placeholder_doi = bool(args.forbid_placeholder_doi)
    post_audit_step2_threshold = float(args.post_audit_step2_same_ratio_threshold)
    post_audit_pitfall2_threshold = float(args.post_audit_pitfall2_same_ratio_threshold)
    post_audit_min_reviewed_at_unique = int(args.post_audit_min_reviewed_at_unique)
    post_audit_similarity_threshold = float(args.post_audit_similarity_threshold)
    min_elapsed_sec = max(0, int(args.enforce_min_elapsed_sec or 0))
    timing_rows = load_timing_log(timing_log_path) if min_elapsed_sec > 0 else []

    guard_ok, guard_payload, guard_log = run_guard_verify(
        root,
        attestation_path,
        queue_path,
        snapshot_path,
        agents_path,
        reviewer_default,
    )
    if not guard_ok:
        checkpoint = {
            "updated_at": utc_now_iso(),
            "error": "attestation_verify_failed",
            "attestation_path": str(attestation_path),
            "guard_verify": guard_payload,
            "guard_log": guard_log,
            "snapshot_path": str(snapshot_path),
            "queue_path": str(queue_path),
            "reviewer_default": reviewer_default,
        }
        save_json(checkpoint_path, checkpoint)
        print(json.dumps(checkpoint, ensure_ascii=False, indent=2))
        return 2

    snapshot_before_bytes = snapshot_path.read_bytes()

    snapshot = load_snapshot(snapshot_path)
    items = snapshot.get("items") if isinstance(snapshot.get("items"), list) else []
    queue = load_queue(queue_path)

    old_checkpoint = load_json(checkpoint_path, {})
    if not isinstance(old_checkpoint, dict):
        old_checkpoint = {}

    defaults_added = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        if not isinstance(item.get("manual_content_v1"), dict):
            item["manual_content_v1"] = default_manual_content(reviewer_default)
            defaults_added += 1

    by_equipment_id, by_doc_id = build_index(items)

    process_all = bool(args.process_all)
    batch_limit = max(1, int(args.batch_size))
    processed_rows = 0
    applied_rows = 0
    fixed_rows = 0

    pending_rows_ordered: List[Tuple[int, Dict[str, Any]]] = []
    applied_rows_ordered: List[Tuple[int, Dict[str, Any]]] = []

    for row_order, row in enumerate(queue):
        status = normalize_text(row.get("status")).lower() or "pending"
        if status == "done":
            continue

        payload = row_payload(row, reviewer_default)
        review = payload.get("review") if isinstance(payload.get("review"), dict) else {}
        target_status = normalize_text(review.get("status")).lower() or "pending"

        if target_status == "pending":
            row["status"] = "pending"
            row["issue_flags"] = []
            pending_rows_ordered.append((row_order, row))
            continue

        if not process_all and processed_rows >= batch_limit:
            pending_rows_ordered.append((row_order, row))
            continue

        idx = resolve_target_index(row, by_equipment_id, by_doc_id)
        if idx == -2:
            mark_needs_manual_fix(row, ["target_item_ambiguous_equipment_id"])
            pending_rows_ordered.append((row_order, row))
            fixed_rows += 1
            processed_rows += 1
            continue
        if idx < 0 or idx >= len(items):
            mark_needs_manual_fix(row, ["target_item_not_found"])
            pending_rows_ordered.append((row_order, row))
            fixed_rows += 1
            processed_rows += 1
            continue

        target_item = items[idx]
        if min_elapsed_sec > 0:
            doc_id = normalize_text(row.get("doc_id")) or normalize_text(target_item.get("doc_id"))
            equipment_id = normalize_text(row.get("equipment_id")) or normalize_text(target_item.get("equipment_id"))
            elapsed = resolve_elapsed_from_log(timing_rows, doc_id, equipment_id)
            if elapsed is None:
                mark_needs_manual_fix(row, ["timing_log_not_found"])
                pending_rows_ordered.append((row_order, row))
                fixed_rows += 1
                processed_rows += 1
                continue
            if elapsed < min_elapsed_sec:
                mark_needs_manual_fix(row, ["timing_elapsed_below_threshold"])
                pending_rows_ordered.append((row_order, row))
                fixed_rows += 1
                processed_rows += 1
                continue
        known_dois = extract_known_dois(target_item)
        normalized, issues = normalize_manual_content(
            payload,
            reviewer_default,
            known_dois,
            beginner_min_chars=beginner_min_chars,
            beginner_max_chars=beginner_max_chars,
            char_count_mode=char_count_mode,
            doc_id=normalize_text(row.get("doc_id")) or normalize_text(target_item.get("doc_id")),
            equipment_id=normalize_text(row.get("equipment_id")) or normalize_text(target_item.get("equipment_id")),
            equipment_name=normalize_text(target_item.get("name")) or normalize_text(row.get("name")),
            forbid_internal_id=forbid_internal_id,
            forbid_placeholder_doi=forbid_placeholder_doi,
        )

        if issues:
            row["manual_content_v1"] = normalized
            mark_needs_manual_fix(row, issues)
            pending_rows_ordered.append((row_order, row))
            fixed_rows += 1
            processed_rows += 1
            continue

        target_item["manual_content_v1"] = normalized
        row["status"] = "done"
        row["issue_flags"] = []
        row["updated_at"] = utc_now_iso()
        row["manual_content_v1"] = normalized
        applied_rows += 1
        processed_rows += 1
        applied_rows_ordered.append((row_order, row))

    snapshot["generated_at"] = utc_now_iso()
    snapshot["count"] = len(items)

    pending_rows = finalize_queue_rows(pending_rows_ordered)
    save_snapshot(snapshot_path, snapshot)
    save_queue(queue_path, pending_rows)

    previous_done = int(old_checkpoint.get("done") or 0)

    checkpoint_base = {
        "updated_at": utc_now_iso(),
        "defaults_added": defaults_added,
        "processed_rows_this_run": processed_rows,
        "applied_rows_this_run": applied_rows,
        "needs_manual_fix_this_run": fixed_rows,
        "done": previous_done + applied_rows,
        "remaining": len(pending_rows),
        "batch_size": batch_limit,
        "process_all": process_all,
        "reviewer_default": reviewer_default,
        "enforce_beginner_min_chars": beginner_min_chars,
        "enforce_beginner_max_chars": beginner_max_chars,
        "char_count_mode": char_count_mode,
        "forbid_internal_id": forbid_internal_id,
        "forbid_placeholder_doi": forbid_placeholder_doi,
        "timing_log_path": str(timing_log_path),
        "enforce_min_elapsed_sec": min_elapsed_sec,
        "snapshot_path": str(snapshot_path),
        "queue_path": str(queue_path),
        "attestation_path": str(attestation_path),
        "guard_verify": guard_payload,
        "post_audit_report_path": str(post_audit_output),
        "post_audit_step2_same_ratio_threshold": post_audit_step2_threshold,
        "post_audit_pitfall2_same_ratio_threshold": post_audit_pitfall2_threshold,
        "post_audit_min_reviewed_at_unique": post_audit_min_reviewed_at_unique,
        "post_audit_similarity_threshold": post_audit_similarity_threshold,
        "post_audit_status": (
            "SKIPPED_NO_APPLY"
            if applied_rows == 0
            else "PENDING_FINAL_BATCH"
            if len(pending_rows) == 0
            else "DEFERRED_UNTIL_BATCH_COMPLETE"
        ),
    }
    save_json(checkpoint_path, checkpoint_base)

    if applied_rows > 0 and len(pending_rows) == 0:
        audit_ok, audit_report, audit_log = run_post_audit(
            root,
            post_audit_script,
            snapshot_path,
            queue_path,
            checkpoint_path,
            attestation_path,
            post_audit_output,
            reviewer_default,
            beginner_min_chars,
            beginner_max_chars,
            char_count_mode,
            post_audit_step2_threshold,
            post_audit_pitfall2_threshold,
            post_audit_min_reviewed_at_unique,
            post_audit_similarity_threshold,
        )

        if not audit_ok:
            snapshot_path.write_bytes(snapshot_before_bytes)

            for _, row in applied_rows_ordered:
                row["status"] = "needs_manual_fix"
                row["issue_flags"] = ["post_audit_failed"]
                row["updated_at"] = utc_now_iso()

            reverted_rows = pending_rows_ordered + applied_rows_ordered
            reverted_queue = finalize_queue_rows(reverted_rows)
            save_queue(queue_path, reverted_queue)

            checkpoint_fail = {
                "updated_at": utc_now_iso(),
                "defaults_added": 0,
                "processed_rows_this_run": processed_rows,
                "applied_rows_this_run": 0,
                "needs_manual_fix_this_run": fixed_rows + len(applied_rows_ordered),
                "done": previous_done,
                "remaining": len(reverted_queue),
                "batch_size": batch_limit,
                "process_all": process_all,
                "reviewer_default": reviewer_default,
                "enforce_beginner_min_chars": beginner_min_chars,
                "enforce_beginner_max_chars": beginner_max_chars,
                "char_count_mode": char_count_mode,
                "forbid_internal_id": forbid_internal_id,
                "forbid_placeholder_doi": forbid_placeholder_doi,
                "snapshot_path": str(snapshot_path),
                "queue_path": str(queue_path),
                "attestation_path": str(attestation_path),
                "guard_verify": guard_payload,
                "post_audit_report_path": str(post_audit_output),
                "post_audit_step2_same_ratio_threshold": post_audit_step2_threshold,
                "post_audit_pitfall2_same_ratio_threshold": post_audit_pitfall2_threshold,
                "post_audit_min_reviewed_at_unique": post_audit_min_reviewed_at_unique,
                "post_audit_similarity_threshold": post_audit_similarity_threshold,
                "post_audit_status": "FAIL",
                "post_audit": audit_report,
                "post_audit_log": audit_log,
                "reverted_rows_this_run": len(applied_rows_ordered),
            }
            save_json(checkpoint_path, checkpoint_fail)
            print(json.dumps(checkpoint_fail, ensure_ascii=False, indent=2))
            return 3

        checkpoint_base["post_audit_status"] = "PASS"
        checkpoint_base["post_audit"] = audit_report
        save_json(checkpoint_path, checkpoint_base)

    print(json.dumps(checkpoint_base, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
