#!/usr/bin/env python3
"""Apply manual translations from queue to snapshot papers."""

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


def has_kana(text: Any) -> bool:
    return bool(re.search(r"[ぁ-んァ-ヶー]", str(text or "")))


def normalize_doi(value: Any) -> str:
    doi = str(value or "").strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    return doi.strip().lower()


def normalize_title_key(value: Any) -> str:
    text = normalize_whitespace(value).lower()
    text = re.sub(r"\s+", " ", text)
    return text


def paper_key(paper: Dict[str, Any]) -> str:
    doi = normalize_doi(paper.get("doi"))
    if doi:
        return f"doi:{doi}"
    title = normalize_title_key(paper.get("title"))
    if title:
        return f"title:{title}"
    return ""


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
        if not isinstance(item, dict):
            continue
        papers = item.get("papers") if isinstance(item.get("papers"), list) else []
        for paper_idx, paper in enumerate(papers):
            if not isinstance(paper, dict):
                continue
            key = paper_key(paper)
            if not key:
                continue
            index.setdefault(key, []).append({"item_idx": item_idx, "paper_idx": paper_idx})
    return index


def translation_issue_flags(abstract: Any, translation_ja: Any) -> List[str]:
    abstract_text = normalize_whitespace(abstract)
    translated_text = normalize_whitespace(translation_ja)
    flags: List[str] = []
    if not translated_text:
        flags.append("missing_ja")
        return flags
    if not has_kana(translated_text):
        flags.append("no_kana")
    if abstract_text and translated_text == abstract_text:
        flags.append("same_as_abstract")
    if len(abstract_text) >= 200 and (
        len(translated_text) / max(1, len(abstract_text))
    ) < 0.35:
        flags.append("too_short_ratio")
    return flags


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply manual translation batch")
    parser.add_argument("--snapshot", default="frontend/dist/equipment_snapshot.json.gz")
    parser.add_argument("--queue", default="tools/manual_translation_queue.jsonl")
    parser.add_argument("--checkpoint", default="tools/manual_translation_checkpoint.json")
    parser.add_argument("--batch-size", type=int, default=25)
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

    pending: List[Dict[str, Any]] = []
    done: List[Dict[str, Any]] = []

    applied_papers = 0
    applied_keys = 0

    for row in queue:
        key = str(row.get("paper_key") or "").strip()
        translation_ja = normalize_whitespace(row.get("translation_ja"))
        if not key or not translation_ja:
            pending.append(row)
            continue

        if not process_all and applied_keys >= batch_limit:
            pending.append(row)
            continue

        matches = index.get(key, [])
        abstract = normalize_whitespace(row.get("abstract"))
        if not abstract and matches:
            first_target = matches[0]
            first_paper = items[int(first_target["item_idx"])]["papers"][int(first_target["paper_idx"])]
            abstract = normalize_whitespace(first_paper.get("abstract"))
        row_flags = translation_issue_flags(abstract, translation_ja)
        if row_flags:
            row["status"] = "needs_manual_fix"
            row["updated_at"] = utc_now_iso()
            row["issue_flags"] = sorted(set(row_flags))
            pending.append(row)
            continue

        if not matches:
            row["status"] = "not_found"
            row["updated_at"] = utc_now_iso()
            done.append(row)
            applied_keys += 1
            continue

        touched = 0
        for target in matches:
            item_idx = int(target["item_idx"])
            paper_idx = int(target["paper_idx"])
            paper = items[item_idx]["papers"][paper_idx]
            paper["abstract_ja"] = translation_ja
            touched += 1

        row["status"] = "done"
        row["updated_at"] = utc_now_iso()
        row["matched_papers"] = touched
        done.append(row)
        applied_keys += 1
        applied_papers += touched

    snapshot["generated_at"] = utc_now_iso()
    snapshot["count"] = len(items)
    save_snapshot(snapshot_path, snapshot)
    save_queue(queue_path, pending)

    total_done = int(checkpoint.get("done") or 0) + len(done)
    stats = {
        "updated_at": utc_now_iso(),
        "processed_keys_this_run": len(done),
        "processed_papers_this_run": applied_papers,
        "done": total_done,
        "remaining": len(pending),
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
