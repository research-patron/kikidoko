#!/usr/bin/env python3
"""Apply manually filled translations from translation_queue.jsonl."""

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
    return normalize_whitespace(value).lower()


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


def row_key(row: Dict[str, Any]) -> str:
    explicit = normalize_whitespace(row.get("paper_key"))
    if explicit:
        return explicit
    return paper_key_from_values(row.get("doi"), row.get("title"))


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
    parser = argparse.ArgumentParser(description="Apply manual translation queue sequentially")
    parser.add_argument("--snapshot", default="frontend/dist/equipment_snapshot.json.gz")
    parser.add_argument("--queue", default="tools/translation_queue.jsonl")
    parser.add_argument("--checkpoint", default="tools/cache/translation_checkpoint.json")
    parser.add_argument("--max-items", type=int, default=0, help="0 means process all")
    parser.add_argument("--translate-timeout", type=float, default=8.0, help="Deprecated no-op")
    parser.add_argument("--sleep", type=float, default=0.0, help="Deprecated no-op")
    args = parser.parse_args()

    root = Path.cwd()
    snapshot_path = (root / args.snapshot).resolve()
    queue_path = (root / args.queue).resolve()
    checkpoint_path = (root / args.checkpoint).resolve()

    if not snapshot_path.exists():
        print("snapshot_not_found")
        return 1

    snapshot = load_snapshot(snapshot_path)
    items = snapshot.get("items") if isinstance(snapshot.get("items"), list) else []
    queue = load_queue(queue_path)
    index = build_index(items)

    max_items = max(0, int(args.max_items))
    processed = 0
    applied_rows = 0
    applied_papers = 0
    remaining: List[Dict[str, Any]] = []

    for row in queue:
        if max_items > 0 and processed >= max_items:
            remaining.append(row)
            continue

        processed += 1
        translation_ja = normalize_whitespace(row.get("translation_ja") or row.get("abstract_ja"))
        if not translation_ja:
            remaining.append(row)
            continue

        key = row_key(row)
        matches = index.get(key, []) if key else []
        abstract = normalize_whitespace(row.get("abstract"))
        if not abstract and matches:
            first_target = matches[0]
            first_paper = items[int(first_target["item_idx"])]["papers"][int(first_target["paper_idx"])]
            abstract = normalize_whitespace(first_paper.get("abstract"))
        row_flags = translation_issue_flags(abstract, translation_ja)
        if row_flags:
            row["updated_at"] = utc_now_iso()
            row["status"] = "needs_manual_fix"
            row["issue_flags"] = sorted(set(row_flags))
            remaining.append(row)
            continue

        touched = 0

        if matches:
            for target in matches:
                item_idx = int(target["item_idx"])
                paper_idx = int(target["paper_idx"])
                paper = items[item_idx]["papers"][paper_idx]
                paper["abstract_ja"] = translation_ja
                touched += 1
        else:
            equipment_id = normalize_whitespace(row.get("equipment_id") or row.get("doc_id"))
            if equipment_id:
                for item in items:
                    item_id = normalize_whitespace(item.get("equipment_id") or item.get("doc_id"))
                    if item_id != equipment_id:
                        continue
                    papers = item.get("papers") if isinstance(item.get("papers"), list) else []
                    for paper in papers:
                        if not isinstance(paper, dict):
                            continue
                        candidate_key = paper_key(paper)
                        if key and candidate_key and candidate_key != key:
                            continue
                        paper["abstract_ja"] = translation_ja
                        touched += 1

        if touched <= 0:
            remaining.append(row)
            continue

        row["updated_at"] = utc_now_iso()
        row["status"] = "done"
        row["matched_papers"] = touched
        applied_rows += 1
        applied_papers += touched

    snapshot["generated_at"] = utc_now_iso()
    snapshot["count"] = len(items)
    save_snapshot(snapshot_path, snapshot)
    save_queue(queue_path, remaining)

    stats = {
        "updated_at": utc_now_iso(),
        "processed": processed,
        "applied_rows": applied_rows,
        "applied_papers": applied_papers,
        "remaining": len(remaining),
        "manual_translation_only": True,
        "network_calls": 0,
    }
    save_json(checkpoint_path, stats)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
