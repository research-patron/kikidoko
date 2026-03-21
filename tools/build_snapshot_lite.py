#!/usr/bin/env python3
"""Build lightweight snapshot compatible with app snapshot schema."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List


KEEP_FIELDS = [
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


def load_gzip_json(path: Path) -> Dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def item_id(item: Dict[str, Any], index: int) -> str:
    for key in ("equipment_id", "doc_id"):
        value = normalize_text(item.get(key))
        if value:
            return value
    return f"item-{index:06d}"


def default_shard(equipment_id: str, shard_count: int) -> str:
    digest = hashlib.md5(equipment_id.encode("utf-8")).digest()
    value = digest[0] % max(1, int(shard_count))
    return f"detail-{value:02x}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build equipment_snapshot_lite-v1.json")
    parser.add_argument("--snapshot", default="frontend/dist/equipment_snapshot.json.gz")
    parser.add_argument("--head", default="frontend/dist/data/equipment_head-v1.json")
    parser.add_argument("--out", default="frontend/dist/data/equipment_snapshot_lite-v1.json")
    parser.add_argument("--shard-count", type=int, default=64)
    args = parser.parse_args()

    root = Path.cwd()
    snapshot_path = (root / args.snapshot).resolve()
    head_path = (root / args.head).resolve()
    out_path = (root / args.out).resolve()

    snapshot = load_gzip_json(snapshot_path)
    head = load_json(head_path) if head_path.exists() else {}

    items = snapshot.get("items") if isinstance(snapshot.get("items"), list) else []
    shard_map = head.get("detail_shard_map") if isinstance(head.get("detail_shard_map"), dict) else {}

    lite_items: List[Dict[str, Any]] = []
    for index, item in enumerate(items):
        source = item if isinstance(item, dict) else {}
        eq_id = item_id(source, index)

        lite: Dict[str, Any] = {}
        for key in KEEP_FIELDS:
            lite[key] = source.get(key)

        lite["equipment_id"] = eq_id
        shard = normalize_text(shard_map.get(eq_id))
        if not shard:
            shard = default_shard(eq_id, int(args.shard_count))
        elif not shard.startswith("detail-"):
            shard = f"detail-{shard}"
        lite["detail_shard"] = shard

        lite_items.append(lite)

    output = {
        "schema_version": snapshot.get("schema_version") or "2",
        "sorted_by": snapshot.get("sorted_by") or "name_ja_asc",
        "generated_at": snapshot.get("generated_at"),
        "project_id": snapshot.get("project_id"),
        "count": len(lite_items),
        "items": lite_items,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(
        json.dumps(
            {
                "count": output["count"],
                "out": str(out_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
