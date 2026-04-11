#!/usr/bin/env python3
"""Build all derived search/detail datasets from equipment snapshot."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


def load_snapshot(path: Path) -> Dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def compact_paper(paper: Dict[str, Any]) -> Dict[str, Any]:
    compact: Dict[str, Any] = {}
    doi = normalize_text(paper.get("doi"))
    title = normalize_text(paper.get("title"))
    url = normalize_text(paper.get("url"))
    year = normalize_text(paper.get("year"))

    if doi:
        compact["doi"] = doi
    if title:
        compact["title"] = title
    if url:
        compact["url"] = url
    if year:
        compact["year"] = year

    return compact


def item_key(item: Dict[str, Any], index: int) -> str:
    candidates = [
        normalize_text(item.get("equipment_id")),
        normalize_text(item.get("doc_id")),
    ]
    for c in candidates:
        if c:
            return c
    return f"item-{index:06d}"


def detail_map_key(item: Dict[str, Any], equipment_id: str) -> str:
    doc_id = normalize_text(item.get("doc_id"))
    if doc_id:
        return doc_id
    return equipment_id


def shard_key(equipment_id: str, shard_count: int) -> str:
    digest = hashlib.md5(equipment_id.encode("utf-8")).digest()
    value = digest[0] % shard_count
    return f"{value:02x}"


def rank_papers_for_head(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def is_good_abstract(value: Any) -> int:
        text = normalize_text(value)
        return 1 if text and not text.startswith("要旨未取得") else 0

    return sorted(
        papers,
        key=lambda p: (
            is_good_abstract(p.get("abstract")),
            1 if normalize_text(p.get("doi")) else 0,
            len(normalize_text(p.get("title"))),
            normalize_text(p.get("year")),
        ),
        reverse=True,
    )


def build_head_item(item: Dict[str, Any], index: int, max_papers: int) -> Dict[str, Any]:
    papers = item.get("papers") if isinstance(item.get("papers"), list) else []
    compact_papers = [compact_paper(p) for p in rank_papers_for_head(papers)[:max_papers]]

    head_item: Dict[str, Any] = {
        "equipment_id": item_key(item, index),
        "doc_id": normalize_text(item.get("doc_id")),
        "name": normalize_text(item.get("name")),
        "category_general": normalize_text(item.get("category_general")),
        "category_detail": normalize_text(item.get("category_detail")),
        "org_name": normalize_text(item.get("org_name")),
        "org_type": normalize_text(item.get("org_type")),
        "prefecture": normalize_text(item.get("prefecture")),
        "region": normalize_text(item.get("region")),
        "external_use": normalize_text(item.get("external_use")),
        "fee_band": normalize_text(item.get("fee_band")),
        "source_url": normalize_text(item.get("source_url")),
        "eqnet_url": normalize_text(item.get("eqnet_url")),
        "eqnet_equipment_id": normalize_text(item.get("eqnet_equipment_id")),
        "eqnet_match_status": normalize_text(item.get("eqnet_match_status")),
        "crawled_at": normalize_text(item.get("crawled_at")),
        "papers_status": normalize_text(item.get("papers_status")),
        "papers_updated_at": normalize_text(item.get("papers_updated_at")),
        "address_raw": normalize_text(item.get("address_raw")),
    }
    if compact_papers:
        head_item["papers"] = compact_papers
    return head_item


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def build_bootstrap_payload(head_payload: Dict[str, Any], search_limit: int) -> Dict[str, Any]:
    items = head_payload.get("items") if isinstance(head_payload.get("items"), list) else []
    pref_counts: Counter[str] = Counter()
    pref_orgs: Dict[str, set] = defaultdict(set)

    for item in items:
      pref = normalize_text(item.get("prefecture"))
      org = normalize_text(item.get("org_name"))
      if pref:
          pref_counts[pref] += 1
      if pref and org:
          pref_orgs[pref].add(org)

    search_head: List[Dict[str, str]] = []
    for item in items[: max(1, int(search_limit))]:
        search_head.append(
            {
                "id": normalize_text(item.get("equipment_id")),
                "name": normalize_text(item.get("name")),
                "prefecture": normalize_text(item.get("prefecture")),
                "org_name": normalize_text(item.get("org_name")),
                "category_general": normalize_text(item.get("category_general")),
                "external_use": normalize_text(item.get("external_use")),
                "fee_band": normalize_text(item.get("fee_band")),
            }
        )

    facility_counts = {pref: len(orgs) for pref, orgs in pref_orgs.items()}
    generated_at = normalize_text(head_payload.get("generated_at"))
    return {
        "version": generated_at or "v1",
        "generated_at": generated_at,
        "coverage_count": len(items),
        "prefecture_counts": dict(pref_counts),
        "facility_counts": facility_counts,
        "search_head": search_head,
        "detail_shard_map": head_payload.get("detail_shard_map")
        if isinstance(head_payload.get("detail_shard_map"), dict)
        else {},
    }


def build_snapshot_lite_payload(
    snapshot_payload: Dict[str, Any],
    items: List[Dict[str, Any]],
    shard_map: Dict[str, str],
    shard_count: int,
) -> Dict[str, Any]:
    keep_fields = [
        "equipment_id",
        "doc_id",
        "name",
        "category_general",
        "category_detail",
        "org_name",
        "org_type",
        "prefecture",
        "region",
        "external_use",
        "fee_band",
        "source_url",
        "eqnet_url",
        "eqnet_equipment_id",
        "eqnet_match_status",
        "crawled_at",
        "papers_status",
        "papers_updated_at",
        "address_raw",
    ]

    lite_items: List[Dict[str, Any]] = []
    for index, item in enumerate(items):
        source = item if isinstance(item, dict) else {}
        eq_id = item_key(source, index)
        detail_id = detail_map_key(source, eq_id)
        lite: Dict[str, Any] = {}
        for key in keep_fields:
            lite[key] = source.get(key)
        lite["equipment_id"] = eq_id
        shard = normalize_text(shard_map.get(detail_id) or shard_map.get(eq_id))
        if not shard:
            shard = f"detail-{shard_key(eq_id, shard_count)}"
        elif not shard.startswith("detail-"):
            shard = f"detail-{shard}"
        lite["detail_shard"] = shard
        lite_items.append(lite)

    return {
        "schema_version": snapshot_payload.get("schema_version") or "2",
        "sorted_by": snapshot_payload.get("sorted_by") or "name_ja_asc",
        "generated_at": snapshot_payload.get("generated_at"),
        "project_id": snapshot_payload.get("project_id"),
        "count": len(lite_items),
        "items": lite_items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build equipment head dataset and detail shards")
    parser.add_argument("--snapshot", default="frontend/dist/equipment_snapshot.json.gz")
    parser.add_argument("--out-dir", default="frontend/dist/data")
    parser.add_argument("--shard-count", type=int, default=64)
    parser.add_argument("--max-head-papers", type=int, default=0)
    parser.add_argument("--search-limit", type=int, default=4500)
    args = parser.parse_args()

    root = Path.cwd()
    snapshot_path = (root / args.snapshot).resolve()
    out_dir = (root / args.out_dir).resolve()

    payload = load_snapshot(snapshot_path)
    items = payload.get("items") if isinstance(payload.get("items"), list) else []

    shard_map: Dict[str, str] = {}
    shards: Dict[str, List[Dict[str, Any]]] = {
        f"{i:02x}": [] for i in range(max(1, int(args.shard_count)))
    }
    head_items: List[Dict[str, Any]] = []

    for idx, item in enumerate(items):
        equipment_id = item_key(item, idx)
        key = shard_key(equipment_id, len(shards))
        shard_map[detail_map_key(item, equipment_id)] = key

        detailed = dict(item)
        detailed["equipment_id"] = equipment_id
        shards[key].append(detailed)

        head_item = build_head_item(item, idx, max(0, int(args.max_head_papers)))
        head_item["equipment_id"] = equipment_id
        head_items.append(head_item)

    head_payload = {
        "schema_version": payload.get("schema_version") or "2",
        "sorted_by": payload.get("sorted_by") or "name_ja_asc",
        "generated_at": payload.get("generated_at"),
        "project_id": payload.get("project_id"),
        "count": len(head_items),
        "detail_shard_map": shard_map,
        "items": head_items,
    }

    write_json(out_dir / "equipment_head-v1.json", head_payload)

    bootstrap_payload = build_bootstrap_payload(head_payload, args.search_limit)
    write_json(out_dir / "bootstrap-v1.json", bootstrap_payload)

    snapshot_lite_payload = build_snapshot_lite_payload(payload, items, shard_map, len(shards))
    write_json(out_dir / "equipment_snapshot_lite-v1.json", snapshot_lite_payload)

    shards_dir = out_dir / "equipment_detail_shards"
    shards_dir.mkdir(parents=True, exist_ok=True)
    for key, shard_items in shards.items():
        shard_payload = {
            "schema_version": payload.get("schema_version") or "2",
            "generated_at": payload.get("generated_at"),
            "count": len(shard_items),
            "shard": key,
            "items": shard_items,
        }
        write_json(shards_dir / f"detail-{key}.json", shard_payload)

    print(
        json.dumps(
            {
                "head_items": len(head_items),
                "shards": len(shards),
                "bootstrap_version": bootstrap_payload.get("version"),
                "snapshot_lite_count": snapshot_lite_payload.get("count"),
                "out_dir": str(out_dir),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
