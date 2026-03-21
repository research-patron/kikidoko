#!/usr/bin/env python3
"""Build manual usage insight queue from snapshot papers."""

from __future__ import annotations

import argparse
import gzip
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


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
    return normalize_whitespace(value).lower()


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


def normalize_research_fields(values: Any) -> List[str]:
    if isinstance(values, list):
        out = []
        for value in values:
            text = normalize_whitespace(value)
            if text and text not in out:
                out.append(text)
        return out[:4]
    return []


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Build manual usage insight queue")
    parser.add_argument("--snapshot", default="frontend/dist/equipment_snapshot.json.gz")
    parser.add_argument("--out", default="tools/manual_usage_insight_queue.jsonl")
    parser.add_argument("--checkpoint", default="tools/manual_usage_insight_checkpoint.json")
    parser.add_argument(
        "--prefill-existing",
        dest="prefill_existing",
        action="store_true",
        default=False,
        help="Prefill existing insight fields from papers when available",
    )
    parser.add_argument(
        "--no-prefill-existing",
        dest="prefill_existing",
        action="store_false",
        help="Do not prefill (default)",
    )
    args = parser.parse_args()

    root = Path.cwd()
    snapshot_path = (root / args.snapshot).resolve()
    out_path = (root / args.out).resolve()
    checkpoint_path = (root / args.checkpoint).resolve()

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
            abstract_ja = normalize_whitespace(paper.get("abstract_ja"))
            usage_how_ja = normalize_whitespace(paper.get("usage_how_ja")) if args.prefill_existing else ""
            usage_what_ja = normalize_whitespace(paper.get("usage_what_ja")) if args.prefill_existing else ""
            research_fields = (
                normalize_research_fields(paper.get("research_fields_ja")) if args.prefill_existing else []
            )
            doi_refs = [normalize_doi(doi)] if normalize_doi(doi) else []

            row = by_key.get(key)
            if not row:
                by_key[key] = {
                    "paper_key": key,
                    "doi": doi,
                    "title": title,
                    "abstract": abstract,
                    "abstract_ja": abstract_ja,
                    "source": source,
                    "year": year,
                    "url": url,
                    "occurrences": 1,
                    "equipment_ids": [equipment_id] if equipment_id else [],
                    "usage_how_ja": usage_how_ja,
                    "usage_what_ja": usage_what_ja,
                    "research_fields_ja": research_fields,
                    "doi_refs": doi_refs,
                    "status": "pending",
                    "updated_at": "",
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
            if args.prefill_existing:
                if usage_how_ja and not row.get("usage_how_ja"):
                    row["usage_how_ja"] = usage_how_ja
                if usage_what_ja and not row.get("usage_what_ja"):
                    row["usage_what_ja"] = usage_what_ja
                existing_fields = row.get("research_fields_ja") if isinstance(row.get("research_fields_ja"), list) else []
                merged_fields = []
                for value in [*existing_fields, *research_fields]:
                    text = normalize_whitespace(value)
                    if text and text not in merged_fields:
                        merged_fields.append(text)
                row["research_fields_ja"] = merged_fields[:4]
            if doi_refs:
                existing_refs = row.get("doi_refs") if isinstance(row.get("doi_refs"), list) else []
                if doi_refs[0] not in existing_refs:
                    existing_refs.append(doi_refs[0])
                row["doi_refs"] = existing_refs[:3]

    rows = list(by_key.values())
    rows.sort(
        key=lambda row: (
            -int(row.get("occurrences") or 0),
            str(row.get("doi") or "").lower(),
            str(row.get("title") or "").lower(),
        )
    )

    for row in rows:
        row["equipment_ids"] = (row.get("equipment_ids") or [])[:20]
        row["doi_refs"] = (row.get("doi_refs") or [])[:3]
        if args.prefill_existing and row.get("usage_how_ja") and row.get("usage_what_ja") and row.get("research_fields_ja"):
            row["status"] = "ready"

    save_queue(out_path, rows)
    pending = sum(1 for row in rows if row.get("status") in {"pending", "needs_manual_fix", "ready"})
    checkpoint = {
        "generated_at": utc_now_iso(),
        "total_unique": len(rows),
        "done": 0,
        "remaining": pending,
        "needs_manual_fix": 0,
        "batch_size_default": 10,
        "prefill_existing": bool(args.prefill_existing),
        "queue_path": str(out_path),
        "snapshot_path": str(snapshot_path),
    }
    save_json(checkpoint_path, checkpoint)
    print(json.dumps(checkpoint, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
