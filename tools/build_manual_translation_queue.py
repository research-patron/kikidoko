#!/usr/bin/env python3
"""Build manual translation queue from snapshot papers."""

from __future__ import annotations

import argparse
import gzip
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


PLACEHOLDER_PREFIX = "要旨未取得"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_whitespace(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


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


def is_good_abstract(text: Any) -> bool:
    value = normalize_whitespace(text)
    return bool(value) and not value.startswith(PLACEHOLDER_PREFIX)


def has_kana(text: Any) -> bool:
    return bool(re.search(r"[ぁ-んァ-ヶー]", str(text or "")))


def has_ellipsis(text: Any) -> bool:
    value = str(text or "")
    return "..." in value or "…" in value


def issue_flags_for_translation(abstract: Any, abstract_ja: Any) -> List[str]:
    abstract_text = normalize_whitespace(abstract)
    abstract_ja_text = normalize_whitespace(abstract_ja)
    flags: List[str] = []

    if not abstract_ja_text:
        flags.append("missing_ja")
    if abstract_text and abstract_ja_text and abstract_text == abstract_ja_text:
        flags.append("same_as_abstract")
    if abstract_ja_text and not has_kana(abstract_ja_text):
        flags.append("no_kana")
    if has_ellipsis(abstract_ja_text) and not has_ellipsis(abstract_text):
        flags.append("ellipsis_mismatch")
    if len(abstract_text) >= 200 and (
        len(abstract_ja_text) / max(1, len(abstract_text))
    ) < 0.35:
        flags.append("too_short_ratio")
    return flags


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


def pick_best_translation(current: str, candidate: str) -> str:
    current = normalize_whitespace(current)
    candidate = normalize_whitespace(candidate)
    if not current:
        return candidate
    if not candidate:
        return current
    if len(candidate) > len(current):
        return candidate
    return current


def main() -> int:
    parser = argparse.ArgumentParser(description="Build manual translation queue")
    parser.add_argument("--snapshot", default="frontend/dist/equipment_snapshot.json.gz")
    parser.add_argument("--out", default="tools/manual_translation_queue.jsonl")
    parser.add_argument("--checkpoint", default="tools/manual_translation_checkpoint.json")
    parser.add_argument(
        "--prefill-existing-ja",
        dest="prefill_existing_ja",
        action="store_true",
        default=False,
        help="Prefill queue rows with current abstract_ja values",
    )
    parser.add_argument(
        "--no-prefill-existing-ja",
        dest="prefill_existing_ja",
        action="store_false",
        help="Do not prefill queue rows with current abstract_ja values (default)",
    )
    parser.add_argument(
        "--problematic-only",
        action="store_true",
        help="Only include rows that violate translation quality rules",
    )
    args = parser.parse_args()

    root = Path.cwd()
    snapshot_path = (root / args.snapshot).resolve()
    out_path = (root / args.out).resolve()
    checkpoint_path = (root / args.checkpoint).resolve()
    prefill_existing_ja = bool(args.prefill_existing_ja)

    if not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")

    snapshot = load_snapshot(snapshot_path)
    items = snapshot.get("items") if isinstance(snapshot.get("items"), list) else []

    by_key: Dict[str, Dict[str, Any]] = {}

    for item in items:
        if not isinstance(item, dict):
            continue
        equipment_id = normalize_whitespace(item.get("equipment_id") or item.get("doc_id"))
        papers = item.get("papers") if isinstance(item.get("papers"), list) else []
        for paper in papers:
            if not isinstance(paper, dict):
                continue
            abstract = normalize_whitespace(paper.get("abstract"))
            if not is_good_abstract(abstract):
                continue
            key = paper_key(paper)
            if not key:
                continue

            doi = normalize_whitespace(paper.get("doi"))
            title = normalize_whitespace(paper.get("title"))
            source = normalize_whitespace(paper.get("source"))
            year = normalize_whitespace(paper.get("year"))
            url = normalize_whitespace(paper.get("url"))
            abstract_ja_existing = normalize_whitespace(paper.get("abstract_ja"))
            issue_flags = issue_flags_for_translation(abstract, abstract_ja_existing)
            if args.problematic_only and not issue_flags:
                continue

            row = by_key.get(key)
            if not row:
                by_key[key] = {
                    "paper_key": key,
                    "doi": doi,
                    "title": title,
                    "abstract": abstract,
                    "translation_ja": abstract_ja_existing if prefill_existing_ja else "",
                    "source": source,
                    "year": year,
                    "url": url,
                    "occurrences": 1,
                    "equipment_ids": [equipment_id] if equipment_id else [],
                    "issue_flags": issue_flags,
                }
                continue

            row["occurrences"] = int(row.get("occurrences") or 0) + 1
            if equipment_id and equipment_id not in row["equipment_ids"]:
                row["equipment_ids"].append(equipment_id)
            if doi and not row.get("doi"):
                row["doi"] = doi
            if title and (not row.get("title") or len(title) > len(str(row.get("title") or ""))):
                row["title"] = title
            if source and not row.get("source"):
                row["source"] = source
            if year and not row.get("year"):
                row["year"] = year
            if url and not row.get("url"):
                row["url"] = url
            if prefill_existing_ja:
                row["translation_ja"] = pick_best_translation(
                    str(row.get("translation_ja") or ""), abstract_ja_existing
                )
            existing_flags = row.get("issue_flags") if isinstance(row.get("issue_flags"), list) else []
            row["issue_flags"] = sorted(set(existing_flags) | set(issue_flags))

    rows = list(by_key.values())
    rows.sort(
        key=lambda r: (
            -int(r.get("occurrences") or 0),
            str(r.get("doi") or "").lower(),
            str(r.get("title") or "").lower(),
        )
    )

    for row in rows:
        row["equipment_ids"] = row["equipment_ids"][:10]
        row["issue_flags"] = sorted(set(row.get("issue_flags") or []))
        row["status"] = "pending"
        row["updated_at"] = ""

    save_queue(out_path, rows)

    pending = sum(1 for row in rows if not normalize_whitespace(row.get("translation_ja")))
    checkpoint = {
        "generated_at": utc_now_iso(),
        "total_unique": len(rows),
        "pending": pending,
        "ready_to_apply": len(rows) - pending,
        "done": 0,
        "batch_size_default": 25,
        "prefill_existing_ja": prefill_existing_ja,
        "problematic_only": bool(args.problematic_only),
        "queue_path": str(out_path),
        "snapshot_path": str(snapshot_path),
    }
    save_json(checkpoint_path, checkpoint)
    print(json.dumps(checkpoint, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
