#!/usr/bin/env python3
"""Build bootstrap-v1.json from equipment head dataset."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def normalize(value: Any) -> str:
    return str(value or "").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build bootstrap data for initial lightweight load")
    parser.add_argument("--head", default="frontend/dist/data/equipment_head-v1.json")
    parser.add_argument("--out", default="frontend/dist/data/bootstrap-v1.json")
    parser.add_argument("--search-limit", type=int, default=4500)
    args = parser.parse_args()

    root = Path.cwd()
    head_path = (root / args.head).resolve()
    out_path = (root / args.out).resolve()

    head = load_json(head_path)
    items = head.get("items") if isinstance(head.get("items"), list) else []

    pref_counts: Counter[str] = Counter()
    pref_orgs: Dict[str, set] = defaultdict(set)

    search_limit = max(1, int(args.search_limit))

    for item in items:
        pref = normalize(item.get("prefecture"))
        org = normalize(item.get("org_name"))
        if pref:
            pref_counts[pref] += 1
        if pref and org:
            pref_orgs[pref].add(org)

    search_head: List[Dict[str, str]] = []
    for item in items[:search_limit]:
        search_head.append(
            {
                "id": normalize(item.get("equipment_id")),
                "name": normalize(item.get("name")),
                "prefecture": normalize(item.get("prefecture")),
                "org_name": normalize(item.get("org_name")),
                "category_general": normalize(item.get("category_general")),
                "external_use": normalize(item.get("external_use")),
                "fee_band": normalize(item.get("fee_band")),
            }
        )

    facility_counts = {pref: len(orgs) for pref, orgs in pref_orgs.items()}

    payload = {
        "version": normalize(head.get("generated_at")) or "v1",
        "generated_at": normalize(head.get("generated_at")),
        "coverage_count": len(items),
        "prefecture_counts": dict(pref_counts),
        "facility_counts": facility_counts,
        "search_head": search_head,
        "detail_shard_map": head.get("detail_shard_map") if isinstance(head.get("detail_shard_map"), dict) else {},
    }

    write_json(out_path, payload)
    print(
        json.dumps(
            {
                "coverage_count": payload["coverage_count"],
                "search_head": len(payload["search_head"]),
                "out": str(out_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
