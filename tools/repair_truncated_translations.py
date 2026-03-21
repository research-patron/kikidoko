#!/usr/bin/env python3
"""Repair bad Japanese translations using manual queue entries only.

Bad translation rules:
- abstract_ja contains "..." or "…" while original abstract does not.
- or abstract length >= 200 and abstract_ja is too short (< 35% of abstract length).
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ELLIPSIS_ASCII = "..."
ELLIPSIS_UNICODE = "…"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_whitespace(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize_doi(value: Any) -> str:
    doi = str(value or "").strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    return doi.strip().lower()


def normalize_title(value: Any) -> str:
    return normalize_whitespace(value).lower()


def paper_key(paper: Dict[str, Any]) -> str:
    doi = normalize_doi(paper.get("doi"))
    if doi:
        return f"doi:{doi}"
    title = normalize_title(paper.get("title"))
    if title:
        return f"title:{title}"
    return ""


def has_ellipsis(text: str) -> bool:
    value = str(text or "")
    return ELLIPSIS_ASCII in value or ELLIPSIS_UNICODE in value


def is_bad_ja_translation(abstract: str, abstract_ja: str) -> bool:
    abs_text = normalize_whitespace(abstract)
    ja_text = normalize_whitespace(abstract_ja)
    if not abs_text or not ja_text:
        return True
    ellipsis_mismatch = has_ellipsis(ja_text) and not has_ellipsis(abs_text)
    too_short = len(abs_text) >= 200 and (len(ja_text) / max(1, len(abs_text))) < 0.35
    return ellipsis_mismatch or too_short


def has_japanese(text: str) -> bool:
    return bool(re.search(r"[ぁ-んァ-ン一-龠々ー]", text or ""))


def load_snapshot(path: Path) -> Dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def save_snapshot(path: Path, payload: Dict[str, Any]) -> None:
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))


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


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
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


def save_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def collect_unique_papers(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    unique: Dict[str, Dict[str, Any]] = {}
    for item_idx, item in enumerate(items):
        papers = item.get("papers") if isinstance(item.get("papers"), list) else []
        for paper_idx, paper in enumerate(papers):
            if not isinstance(paper, dict):
                continue
            key = paper_key(paper)
            if not key:
                continue
            abstract = normalize_whitespace(paper.get("abstract"))
            abstract_ja = normalize_whitespace(paper.get("abstract_ja"))
            ref = {"item_idx": item_idx, "paper_idx": paper_idx}
            row = unique.get(key)
            if not row:
                unique[key] = {
                    "paper_key": key,
                    "doi": normalize_whitespace(paper.get("doi")),
                    "title": normalize_whitespace(paper.get("title")),
                    "abstract": abstract,
                    "abstract_ja": abstract_ja,
                    "refs": [ref],
                }
                continue
            row["refs"].append(ref)
            if len(abstract) > len(str(row.get("abstract") or "")):
                row["abstract"] = abstract
            if len(abstract_ja) > len(str(row.get("abstract_ja") or "")):
                row["abstract_ja"] = abstract_ja
            if not row.get("doi") and normalize_whitespace(paper.get("doi")):
                row["doi"] = normalize_whitespace(paper.get("doi"))
            if len(normalize_whitespace(paper.get("title"))) > len(str(row.get("title") or "")):
                row["title"] = normalize_whitespace(paper.get("title"))
    return unique


def count_bad_unique(unique_rows: Dict[str, Dict[str, Any]]) -> int:
    count = 0
    for row in unique_rows.values():
        if is_bad_ja_translation(str(row.get("abstract") or ""), str(row.get("abstract_ja") or "")):
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair truncated Japanese translations (manual queue only)")
    parser.add_argument("--snapshot", default="frontend/dist/equipment_snapshot.json.gz")
    parser.add_argument("--manual-queue", default="tools/manual_translation_queue.jsonl")
    parser.add_argument("--checkpoint", default="tools/cache/repair_truncated_translations_checkpoint.json")
    parser.add_argument("--unresolved", default="tools/cache/repair_truncated_translations_unresolved.jsonl")
    parser.add_argument("--process-bad-only", action="store_true")
    parser.add_argument("--max-items", type=int, default=0, help="0 means process all targets")
    parser.add_argument("--append-manual-queue", action="store_true")
    args = parser.parse_args()

    root = Path.cwd()
    snapshot_path = (root / args.snapshot).resolve()
    manual_queue_path = (root / args.manual_queue).resolve()
    checkpoint_path = (root / args.checkpoint).resolve()
    unresolved_path = (root / args.unresolved).resolve()

    snapshot = load_snapshot(snapshot_path)
    items = snapshot.get("items") if isinstance(snapshot.get("items"), list) else []
    unique_rows = collect_unique_papers(items)
    total_unique = len(unique_rows)
    bad_before = count_bad_unique(unique_rows)

    manual_rows = load_jsonl(manual_queue_path)
    manual_map: Dict[str, str] = {}
    for row in manual_rows:
        key = normalize_whitespace(row.get("paper_key"))
        translation = normalize_whitespace(row.get("translation_ja") or row.get("abstract_ja"))
        if key and translation and has_japanese(translation):
            manual_map[key] = translation

    candidates: List[Dict[str, Any]] = []
    for row in unique_rows.values():
        row_bad = is_bad_ja_translation(str(row.get("abstract") or ""), str(row.get("abstract_ja") or ""))
        if args.process_bad_only and not row_bad:
            continue
        candidates.append(row)

    candidates.sort(key=lambda row: str(row.get("paper_key") or ""))
    max_items = max(0, int(args.max_items))
    targets = candidates if max_items == 0 else candidates[:max_items]

    fixed = 0
    applied_refs = 0
    unresolved: List[Dict[str, Any]] = []

    for row in targets:
        key = str(row.get("paper_key") or "")
        abstract = normalize_whitespace(row.get("abstract"))
        translated = normalize_whitespace(manual_map.get(key, ""))

        if not translated:
            unresolved.append(
                {
                    "paper_key": key,
                    "doi": row.get("doi"),
                    "title": row.get("title"),
                    "abstract": abstract,
                    "reason": "manual_translation_required",
                }
            )
            continue

        if is_bad_ja_translation(abstract, translated):
            unresolved.append(
                {
                    "paper_key": key,
                    "doi": row.get("doi"),
                    "title": row.get("title"),
                    "abstract": abstract,
                    "reason": "manual_translation_still_bad",
                }
            )
            continue

        refs = row.get("refs") if isinstance(row.get("refs"), list) else []
        touched = 0
        for ref in refs:
            item_idx = int(ref.get("item_idx"))
            paper_idx = int(ref.get("paper_idx"))
            try:
                items[item_idx]["papers"][paper_idx]["abstract_ja"] = translated
                touched += 1
            except Exception:
                continue
        if touched > 0:
            fixed += 1
            applied_refs += touched

    if args.append_manual_queue:
        by_key: Dict[str, Dict[str, Any]] = {}
        for row in manual_rows:
            key = normalize_whitespace(row.get("paper_key"))
            if key:
                by_key[key] = row
        for row in unresolved:
            key = str(row.get("paper_key") or "")
            if not key:
                continue
            existing = by_key.get(key)
            if existing:
                continue
            by_key[key] = {
                "paper_key": key,
                "doi": normalize_whitespace(row.get("doi")),
                "title": normalize_whitespace(row.get("title")),
                "abstract": normalize_whitespace(row.get("abstract")),
                "translation_ja": "",
                "status": "pending",
                "updated_at": "",
            }
        merged_rows = list(by_key.values())
        merged_rows.sort(key=lambda row: str(row.get("paper_key") or ""))
        save_jsonl(manual_queue_path, merged_rows)

    snapshot["generated_at"] = utc_now_iso()
    snapshot["count"] = len(items)
    save_snapshot(snapshot_path, snapshot)

    verify = load_snapshot(snapshot_path)
    verify_items = verify.get("items") if isinstance(verify.get("items"), list) else []
    bad_after = count_bad_unique(collect_unique_papers(verify_items))

    checkpoint = {
        "updated_at": utc_now_iso(),
        "snapshot_path": str(snapshot_path),
        "manual_queue_path": str(manual_queue_path),
        "total_unique": total_unique,
        "bad_before": bad_before,
        "targets": len(targets),
        "fixed": fixed,
        "applied_refs": applied_refs,
        "unresolved": len(unresolved),
        "bad_after": bad_after,
        "manual_translation_only": True,
        "network_calls": 0,
        "process_bad_only": bool(args.process_bad_only),
        "max_items": int(args.max_items),
    }

    save_json(checkpoint_path, checkpoint)
    save_jsonl(unresolved_path, unresolved)
    print(json.dumps(checkpoint, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
