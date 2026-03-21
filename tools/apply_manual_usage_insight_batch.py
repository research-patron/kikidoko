#!/usr/bin/env python3
"""Apply manual usage insights from queue to snapshot papers."""

from __future__ import annotations

import argparse
import gzip
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_whitespace(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize_doi(value: Any) -> str:
    doi = str(value or "").strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    return doi.strip().lower()


def normalize_title_key(value: Any) -> str:
    return normalize_whitespace(value).lower()


def has_japanese(text: Any) -> bool:
    return bool(re.search(r"[ぁ-んァ-ン一-龠々ー]", str(text or "")))


def paper_key_from_values(doi: Any, title: Any) -> str:
    doi_norm = normalize_doi(doi)
    if doi_norm:
        return f"doi:{doi_norm}"
    title_norm = normalize_title_key(title)
    if title_norm:
        return f"title:{title_norm}"
    return ""


def paper_key(paper: Dict[str, Any]) -> str:
    return paper_key_from_values(paper.get("doi"), paper.get("title"))


def row_key(row: Dict[str, Any]) -> str:
    explicit = normalize_whitespace(row.get("paper_key"))
    if explicit:
        return explicit
    return paper_key_from_values(row.get("doi"), row.get("title"))


def normalize_research_fields(values: Any) -> List[str]:
    if isinstance(values, list):
        out = []
        for value in values:
            text = normalize_whitespace(value)
            if text and text not in out:
                out.append(text)
        return out[:4]
    return []


def normalize_doi_refs(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    out = []
    for value in values:
        doi = normalize_doi(value)
        if doi and doi not in out:
            out.append(doi)
    return out[:3]


def validate_row_payload(row: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    usage_how_ja = normalize_whitespace(row.get("usage_how_ja"))
    usage_what_ja = normalize_whitespace(row.get("usage_what_ja"))
    fields = normalize_research_fields(row.get("research_fields_ja"))
    doi_refs = normalize_doi_refs(row.get("doi_refs"))

    if len(usage_how_ja) < 20 or not has_japanese(usage_how_ja):
        issues.append("invalid_usage_how_ja")
    if len(usage_what_ja) < 20 or not has_japanese(usage_what_ja):
        issues.append("invalid_usage_what_ja")
    if not (1 <= len(fields) <= 4):
        issues.append("invalid_research_fields_count")
    else:
        if any(not has_japanese(field) for field in fields):
            issues.append("invalid_research_field_language")
    if len(doi_refs) < 1:
        issues.append("missing_doi_refs")
    return issues


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


def build_index(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, int]]]:
    index: Dict[str, List[Dict[str, int]]] = {}
    for item_idx, item in enumerate(items):
        papers = item.get("papers") if isinstance(item.get("papers"), list) else []
        for paper_idx, paper in enumerate(papers):
            if not isinstance(paper, dict):
                continue
            key = paper_key(paper)
            if not key:
                continue
            index.setdefault(key, []).append({"item_idx": item_idx, "paper_idx": paper_idx})
    return index


def build_item_usage_insights(item: Dict[str, Any]) -> Dict[str, Any] | None:
    papers = item.get("papers") if isinstance(item.get("papers"), list) else []
    if not papers:
        return None

    selected = None
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        how = normalize_whitespace(paper.get("usage_how_ja"))
        what = normalize_whitespace(paper.get("usage_what_ja"))
        fields = normalize_research_fields(paper.get("research_fields_ja"))
        if how and what and fields:
            selected = paper
            break
    if not selected:
        return None

    doi = normalize_doi(selected.get("doi"))
    refs = [doi] if doi else []
    how_text = normalize_whitespace(selected.get("usage_how_ja"))
    what_text = normalize_whitespace(selected.get("usage_what_ja"))
    fields = normalize_research_fields(selected.get("research_fields_ja"))

    return {
        "how": {"text": how_text, "doi_refs": refs},
        "what": {"text": what_text, "doi_refs": refs},
        "fields": {"items": fields, "doi_refs": refs},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply manual usage insight batch")
    parser.add_argument("--snapshot", default="frontend/dist/equipment_snapshot.json.gz")
    parser.add_argument("--queue", default="tools/manual_usage_insight_queue.jsonl")
    parser.add_argument("--checkpoint", default="tools/manual_usage_insight_checkpoint.json")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--process-all", action="store_true")
    args = parser.parse_args()

    root = Path.cwd()
    snapshot_path = (root / args.snapshot).resolve()
    queue_path = (root / args.queue).resolve()
    checkpoint_path = (root / args.checkpoint).resolve()

    snapshot = load_snapshot(snapshot_path)
    items = snapshot.get("items") if isinstance(snapshot.get("items"), list) else []
    queue = load_queue(queue_path)
    checkpoint = load_json(checkpoint_path, {})
    if not isinstance(checkpoint, dict):
        checkpoint = {}

    index = build_index(items)

    batch_limit = max(1, int(args.batch_size))
    process_all = bool(args.process_all)
    processed_keys = 0
    processed_papers = 0
    done_rows = 0
    pending_rows: List[Dict[str, Any]] = []
    needs_manual_fix = 0

    for row in queue:
        key = row_key(row)
        if not key:
            row["status"] = "needs_manual_fix"
            row["issue_flags"] = ["missing_paper_key"]
            row["updated_at"] = utc_now_iso()
            needs_manual_fix += 1
            pending_rows.append(row)
            continue

        has_payload = bool(
            normalize_whitespace(row.get("usage_how_ja"))
            and normalize_whitespace(row.get("usage_what_ja"))
            and normalize_research_fields(row.get("research_fields_ja"))
        )
        if not has_payload:
            row["status"] = "pending"
            pending_rows.append(row)
            continue

        if not process_all and done_rows >= batch_limit:
            pending_rows.append(row)
            continue

        issues = validate_row_payload(row)
        if issues:
            row["status"] = "needs_manual_fix"
            row["issue_flags"] = sorted(set(issues))
            row["updated_at"] = utc_now_iso()
            needs_manual_fix += 1
            pending_rows.append(row)
            continue

        matches = index.get(key, [])
        if not matches:
            row["status"] = "not_found"
            row["updated_at"] = utc_now_iso()
            done_rows += 1
            processed_keys += 1
            continue

        usage_how_ja = normalize_whitespace(row.get("usage_how_ja"))
        usage_what_ja = normalize_whitespace(row.get("usage_what_ja"))
        research_fields = normalize_research_fields(row.get("research_fields_ja"))
        touched = 0
        touched_item_indexes = set()
        for target in matches:
            item_idx = int(target["item_idx"])
            paper_idx = int(target["paper_idx"])
            paper = items[item_idx]["papers"][paper_idx]
            paper["usage_how_ja"] = usage_how_ja
            paper["usage_what_ja"] = usage_what_ja
            paper["research_fields_ja"] = research_fields
            touched += 1
            touched_item_indexes.add(item_idx)

        for item_idx in touched_item_indexes:
            item = items[item_idx]
            insights = build_item_usage_insights(item)
            if insights:
                item["usage_insights"] = insights
            else:
                item.pop("usage_insights", None)

        row["status"] = "done"
        row["matched_papers"] = touched
        row["updated_at"] = utc_now_iso()
        done_rows += 1
        processed_keys += 1
        processed_papers += touched

    snapshot["generated_at"] = utc_now_iso()
    snapshot["count"] = len(items)
    save_snapshot(snapshot_path, snapshot)
    save_queue(queue_path, pending_rows)

    previous_done = int(checkpoint.get("done") or 0)
    stats = {
        "updated_at": utc_now_iso(),
        "processed_keys_this_run": processed_keys,
        "processed_papers_this_run": processed_papers,
        "done": previous_done + done_rows,
        "remaining": len(pending_rows),
        "needs_manual_fix": needs_manual_fix,
        "batch_size": batch_limit,
        "process_all": process_all,
        "snapshot_path": str(snapshot_path),
        "queue_path": str(queue_path),
    }
    save_json(checkpoint_path, stats)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
