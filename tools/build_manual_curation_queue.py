#!/usr/bin/env python3
"""Build manual curation queue for equipment manual content."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from family_rules import build_family_id, item_primary_id, select_deterministic_by_family

DEFAULT_REVIEWER = "codex-manual"

EXTERNAL_USE_PRIORITY = {
    "可": 0,
    "要相談": 1,
    "不明": 2,
    "不可": 3,
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def load_snapshot(path: Path) -> Dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_queue(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def default_manual_content(reviewer: str) -> Dict[str, Any]:
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


def item_key(item: Dict[str, Any], index: int) -> str:
    doc_id = normalize_text(item.get("doc_id"))
    if doc_id:
        return doc_id
    equipment_id = normalize_text(item.get("equipment_id"))
    if equipment_id:
        return equipment_id
    return f"item-{index:06d}"


def rank_key(item: Dict[str, Any], index: int) -> Tuple[Any, ...]:
    papers = item.get("papers") if isinstance(item.get("papers"), list) else []
    papers_count = len(papers)
    external_use = normalize_text(item.get("external_use"))
    ext_priority = EXTERNAL_USE_PRIORITY.get(external_use, 9)
    name = normalize_text(item.get("name"))
    return (
        -papers_count,
        ext_priority,
        name,
        item_key(item, index),
    )


def rank_key_beginner(item: Dict[str, Any], index: int) -> Tuple[str, str, str]:
    category = normalize_text(item.get("category_general")) or "未分類"
    name = normalize_text(item.get("name"))
    doc_or_eq = normalize_text(item.get("doc_id")) or normalize_text(item.get("equipment_id")) or item_key(item, index)
    return (category, name, doc_or_eq)


def review_status_of(item: Dict[str, Any]) -> str:
    manual = item.get("manual_content_v1") if isinstance(item.get("manual_content_v1"), dict) else {}
    review = manual.get("review") if isinstance(manual.get("review"), dict) else {}
    status = normalize_text(review.get("status")).lower()
    if status in {"approved", "pending", "rejected"}:
        return status
    return "pending"


def count_chars(text: Any, mode: str) -> int:
    raw = str(text or "")
    if mode == "non_whitespace":
        return len(re.sub(r"\s+", "", raw))
    return len(raw.strip())


def beginner_char_count(item: Dict[str, Any], mode: str) -> int:
    manual = item.get("manual_content_v1") if isinstance(item.get("manual_content_v1"), dict) else {}
    beginner = manual.get("beginner_guide") if isinstance(manual.get("beginner_guide"), dict) else {}
    principle = normalize_text(beginner.get("principle_ja"))
    sample = normalize_text(beginner.get("sample_guidance_ja"))
    steps = beginner.get("basic_steps_ja") if isinstance(beginner.get("basic_steps_ja"), list) else []
    pitfalls = beginner.get("common_pitfalls_ja") if isinstance(beginner.get("common_pitfalls_ja"), list) else []
    text = "".join(
        [
            principle,
            sample,
            "".join(normalize_text(v) for v in steps if normalize_text(v)),
            "".join(normalize_text(v) for v in pitfalls if normalize_text(v)),
        ]
    )
    return count_chars(text, mode)


def compact_papers(item: Dict[str, Any], max_items: int = 3) -> List[Dict[str, str]]:
    papers = item.get("papers") if isinstance(item.get("papers"), list) else []
    out: List[Dict[str, str]] = []
    for paper in papers[:max_items]:
        if not isinstance(paper, dict):
            continue
        out.append(
            {
                "doi": normalize_text(paper.get("doi")),
                "title": normalize_text(paper.get("title")),
                "year": normalize_text(paper.get("year")),
                "url": normalize_text(paper.get("url")),
            }
        )
    return out


def clone_manual_content(item: Dict[str, Any], reviewer: str) -> Dict[str, Any]:
    current = item.get("manual_content_v1")
    if isinstance(current, dict):
        return json.loads(json.dumps(current, ensure_ascii=False))
    return default_manual_content(reviewer)


def select_round_robin(grouped: Dict[str, List[Tuple[int, Dict[str, Any]]]], limit: int) -> List[Tuple[int, Dict[str, Any]]]:
    categories = sorted(grouped.keys())
    if limit <= 0 or not categories:
        return []

    pointers = {category: 0 for category in categories}
    selected: List[Tuple[int, Dict[str, Any]]] = []

    while len(selected) < limit:
        picked_this_round = 0
        for category in categories:
            rows = grouped.get(category) or []
            cursor = int(pointers.get(category, 0))
            if cursor >= len(rows):
                continue
            selected.append(rows[cursor])
            pointers[category] = cursor + 1
            picked_this_round += 1
            if len(selected) >= limit:
                break
        if picked_this_round == 0:
            break

    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description="Build manual curation queue")
    parser.add_argument("--snapshot", default="frontend/dist/equipment_snapshot.json.gz")
    parser.add_argument("--out", default="tools/manual_curation_queue.jsonl")
    parser.add_argument("--checkpoint", default="tools/manual_curation_checkpoint.json")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--reviewer", default=DEFAULT_REVIEWER)
    parser.add_argument("--batch-id", default="")
    parser.add_argument(
        "--campaign",
        default="default",
        choices=["default", "beginner-longform"],
        help="Queue campaign type.",
    )
    parser.add_argument(
        "--include-reviewed",
        action="store_true",
        help="Include items already reviewed (approved/rejected). Default excludes them.",
    )
    parser.add_argument(
        "--ignore-papers-filter",
        action="store_true",
        help="Skip papers_status/papers filters in default campaign.",
    )
    parser.add_argument("--min-beginner-chars", type=int, default=0)
    parser.add_argument(
        "--char-count-mode",
        default="non_whitespace",
        choices=["non_whitespace", "raw"],
    )
    parser.add_argument(
        "--family-mode",
        default="none",
        choices=["none", "deterministic"],
        help="Family grouping mode for beginner-longform campaign.",
    )
    parser.add_argument(
        "--family-map-out",
        default="tools/manual_family_map.json",
        help="Output path for doc/equipment to family_id map.",
    )
    parser.add_argument(
        "--family-groups-out",
        default="",
        help="Optional output path for selected family groups JSON.",
    )
    args = parser.parse_args()

    root = Path.cwd()
    snapshot_path = (root / args.snapshot).resolve()
    out_path = (root / args.out).resolve()
    checkpoint_path = (root / args.checkpoint).resolve()
    family_map_out_path = (root / args.family_map_out).resolve()

    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")

    snapshot = load_snapshot(snapshot_path)
    items = snapshot.get("items") if isinstance(snapshot.get("items"), list) else []

    campaign = normalize_text(args.campaign).lower() or "default"
    family_mode = normalize_text(args.family_mode).lower() or "none"
    min_beginner_chars = max(0, int(args.min_beginner_chars))
    batch_id = normalize_text(args.batch_id) or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    family_groups_out_raw = normalize_text(args.family_groups_out)
    family_groups_out_path = (
        (root / family_groups_out_raw).resolve()
        if family_groups_out_raw
        else (root / f"tools/manual_family_groups_{batch_id}.json").resolve()
    )

    family_map: Dict[str, str] = {}
    if family_mode == "deterministic":
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            family_map[item_primary_id(item, idx)] = build_family_id(item)

    eligible: List[Tuple[int, Dict[str, Any]]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if campaign == "beginner-longform":
            if min_beginner_chars > 0 and beginner_char_count(item, args.char_count_mode) >= min_beginner_chars:
                continue
            eligible.append((idx, item))
            continue

        if not args.ignore_papers_filter and normalize_text(item.get("papers_status")) != "ready":
            continue
        if not args.include_reviewed and review_status_of(item) in {"approved", "rejected"}:
            continue
        papers = item.get("papers") if isinstance(item.get("papers"), list) else []
        if not args.ignore_papers_filter and not papers:
            continue
        eligible.append((idx, item))

    grouped: Dict[str, List[Tuple[int, Dict[str, Any]]]] = {}
    grouped_by_family: Dict[str, List[Tuple[int, Dict[str, Any]]]] = {}
    if campaign == "beginner-longform":
        eligible.sort(key=lambda pair: rank_key_beginner(pair[1], pair[0]))
        if family_mode == "deterministic":
            selected, grouped_by_family = select_deterministic_by_family(eligible, max(0, int(args.limit)))
        else:
            selected = eligible[: max(0, int(args.limit))]
    else:
        for idx, item in eligible:
            category = normalize_text(item.get("category_general")) or "未分類"
            grouped.setdefault(category, []).append((idx, item))

        for category, rows in grouped.items():
            rows.sort(key=lambda pair: rank_key(pair[1], pair[0]))

        selected = select_round_robin(grouped, max(0, int(args.limit)))

    queue_rows: List[Dict[str, Any]] = []
    for idx, item in selected:
        beginner_chars = beginner_char_count(item, args.char_count_mode)
        primary_id = item_primary_id(item, idx)
        family_id = family_map.get(primary_id, "")
        queue_rows.append(
            {
                "equipment_id": normalize_text(item.get("equipment_id")) or item_key(item, idx),
                "doc_id": normalize_text(item.get("doc_id")),
                "name": normalize_text(item.get("name")),
                "category_general": normalize_text(item.get("category_general")) or "未分類",
                "category_detail": normalize_text(item.get("category_detail")),
                "org_name": normalize_text(item.get("org_name")),
                "prefecture": normalize_text(item.get("prefecture")),
                "external_use": normalize_text(item.get("external_use")),
                "source_url": normalize_text(item.get("source_url")),
                "papers_count": len(item.get("papers") if isinstance(item.get("papers"), list) else []),
                "paper_candidates": compact_papers(item, max_items=3),
                "family_id": family_id,
                "beginner_non_ws_chars": beginner_chars,
                "manual_content_v1": (
                    clone_manual_content(item, args.reviewer)
                    if campaign == "beginner-longform"
                    else default_manual_content(args.reviewer)
                ),
                "status": "pending",
                "issue_flags": [],
                "updated_at": "",
            }
        )

    save_queue(out_path, queue_rows)
    queue_sha256 = sha256_file(out_path)

    if family_mode == "deterministic":
        family_map_payload = {
            "generated_at": utc_now_iso(),
            "batch_id": batch_id,
            "snapshot_path": str(snapshot_path),
            "campaign": campaign,
            "family_mode": family_mode,
            "count": len(family_map),
            "doc_to_family_id": family_map,
        }
        save_json(family_map_out_path, family_map_payload)

        selected_groups: Dict[str, List[Dict[str, Any]]] = {}
        for row in queue_rows:
            family_id = normalize_text(row.get("family_id")) or "unknown"
            selected_groups.setdefault(family_id, []).append(
                {
                    "doc_id": normalize_text(row.get("doc_id")),
                    "equipment_id": normalize_text(row.get("equipment_id")),
                    "name": normalize_text(row.get("name")),
                    "category_general": normalize_text(row.get("category_general")),
                    "category_detail": normalize_text(row.get("category_detail")),
                }
            )
        group_rows: List[Dict[str, Any]] = []
        for family_id in sorted(selected_groups.keys()):
            members = selected_groups[family_id]
            group_rows.append(
                {
                    "family_id": family_id,
                    "count": len(members),
                    "members": members,
                }
            )
        family_group_payload = {
            "generated_at": utc_now_iso(),
            "batch_id": batch_id,
            "campaign": campaign,
            "family_mode": family_mode,
            "selected_count": len(queue_rows),
            "family_count": len(group_rows),
            "groups": group_rows,
            "eligible_family_count": len(grouped_by_family),
        }
        save_json(family_groups_out_path, family_group_payload)

    checkpoint = {
        "generated_at": utc_now_iso(),
        "batch_id": batch_id,
        "queue_sha256": queue_sha256,
        "target_count": max(0, int(args.limit)),
        "selected_count": len(queue_rows),
        "eligible_count": len(eligible),
        "category_count": len(grouped),
        "campaign": campaign,
        "family_mode": family_mode,
        "include_reviewed": bool(args.include_reviewed or campaign == "beginner-longform"),
        "ignore_papers_filter": bool(args.ignore_papers_filter),
        "min_beginner_chars": min_beginner_chars,
        "char_count_mode": args.char_count_mode,
        "queue_path": str(out_path),
        "snapshot_path": str(snapshot_path),
        "reviewer_default": normalize_text(args.reviewer) or DEFAULT_REVIEWER,
        "family_map_path": str(family_map_out_path) if family_mode == "deterministic" else "",
        "family_groups_path": str(family_groups_out_path) if family_mode == "deterministic" else "",
        "eligible_family_count": len(grouped_by_family) if family_mode == "deterministic" else 0,
    }
    save_json(checkpoint_path, checkpoint)
    print(json.dumps(checkpoint, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
