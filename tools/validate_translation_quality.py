#!/usr/bin/env python3
"""Validate translation quality gates for equipment snapshot papers."""

from __future__ import annotations

import argparse
import gzip
import json
import re
from pathlib import Path
from typing import Any, Dict, List

ELLIPSIS_ASCII = "..."
ELLIPSIS_UNICODE = "…"


def normalize_whitespace(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def has_ellipsis(text: str) -> bool:
    value = str(text or "")
    return ELLIPSIS_ASCII in value or ELLIPSIS_UNICODE in value


def has_kana(text: str) -> bool:
    return bool(re.search(r"[ぁ-んァ-ヶー]", text or ""))


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


def load_snapshot(path: Path) -> Dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def issue_flags(abstract: Any, abstract_ja: Any) -> List[str]:
    abstract_text = normalize_whitespace(abstract)
    abstract_ja_text = normalize_whitespace(abstract_ja)
    flags: List[str] = []

    if not abstract_ja_text:
        flags.append("empty")
    if abstract_text and abstract_ja_text and abstract_text == abstract_ja_text:
        flags.append("same_as_english")
    if abstract_ja_text and not has_kana(abstract_ja_text):
        flags.append("no_kana")
    if has_ellipsis(abstract_ja_text) and not has_ellipsis(abstract_text):
        flags.append("ellipsis")
    if len(abstract_text) >= 200 and (len(abstract_ja_text) / max(1, len(abstract_text))) < 0.35:
        flags.append("short")
    return flags


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate abstract_ja quality gates")
    parser.add_argument("--snapshot", default="frontend/dist/equipment_snapshot.json.gz")
    parser.add_argument("--max-ellipsis", type=int, default=0)
    parser.add_argument("--max-short", type=int, default=0)
    parser.add_argument("--max-empty", type=int, default=0)
    parser.add_argument("--max-no-kana", type=int, default=0)
    parser.add_argument("--max-same-as-english", type=int, default=0)
    args = parser.parse_args()

    root = Path.cwd()
    snapshot_path = (root / args.snapshot).resolve()
    payload = load_snapshot(snapshot_path)
    items = payload.get("items") if isinstance(payload.get("items"), list) else []

    papers_total = 0
    bad_ellipsis = 0
    bad_short = 0
    bad_empty = 0
    bad_no_kana = 0
    bad_same_as_english = 0

    unique_map: Dict[str, Dict[str, str]] = {}

    for item in items:
        papers = item.get("papers") if isinstance(item.get("papers"), list) else []
        for paper in papers:
            if not isinstance(paper, dict):
                continue
            papers_total += 1
            abstract = normalize_whitespace(paper.get("abstract"))
            abstract_ja = normalize_whitespace(paper.get("abstract_ja"))
            key = paper_key(paper)
            if key and key not in unique_map:
                unique_map[key] = {"abstract": abstract, "abstract_ja": abstract_ja}

            flags = issue_flags(abstract, abstract_ja)
            if "empty" in flags:
                bad_empty += 1
            if "ellipsis" in flags:
                bad_ellipsis += 1
            if "short" in flags:
                bad_short += 1
            if "no_kana" in flags:
                bad_no_kana += 1
            if "same_as_english" in flags:
                bad_same_as_english += 1

    unique_bad_ellipsis = 0
    unique_bad_short = 0
    unique_bad_empty = 0
    unique_bad_no_kana = 0
    unique_bad_same_as_english = 0
    for row in unique_map.values():
        abstract = row["abstract"]
        abstract_ja = row["abstract_ja"]
        flags = issue_flags(abstract, abstract_ja)
        if "empty" in flags:
            unique_bad_empty += 1
        if "ellipsis" in flags:
            unique_bad_ellipsis += 1
        if "short" in flags:
            unique_bad_short += 1
        if "no_kana" in flags:
            unique_bad_no_kana += 1
        if "same_as_english" in flags:
            unique_bad_same_as_english += 1

    stats = {
        "items": len(items),
        "papers_total": papers_total,
        "papers_unique": len(unique_map),
        "bad_ellipsis": bad_ellipsis,
        "bad_short": bad_short,
        "bad_empty": bad_empty,
        "bad_no_kana": bad_no_kana,
        "bad_same_as_english": bad_same_as_english,
        "unique_bad_ellipsis": unique_bad_ellipsis,
        "unique_bad_short": unique_bad_short,
        "unique_bad_empty": unique_bad_empty,
        "unique_bad_no_kana": unique_bad_no_kana,
        "unique_bad_same_as_english": unique_bad_same_as_english,
        "max_ellipsis": int(args.max_ellipsis),
        "max_short": int(args.max_short),
        "max_empty": int(args.max_empty),
        "max_no_kana": int(args.max_no_kana),
        "max_same_as_english": int(args.max_same_as_english),
    }
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    if bad_ellipsis > int(args.max_ellipsis):
        return 1
    if bad_short > int(args.max_short):
        return 1
    if bad_empty > int(args.max_empty):
        return 1
    if bad_no_kana > int(args.max_no_kana):
        return 1
    if bad_same_as_english > int(args.max_same_as_english):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
