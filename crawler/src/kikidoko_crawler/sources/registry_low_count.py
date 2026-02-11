from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..models import RawEquipment
from ..utils import clean_text
from .table_utils import TableConfig, fetch_table_records

REGISTRY_PATH = Path(__file__).resolve().parents[3] / "config" / "source_registry_low_count.json"


@dataclass(frozen=True)
class RegistryEntry:
    key: str
    org_name: str
    prefecture: str
    url: str
    parser_type: str
    category_hint: str
    external_use: str
    selectors: dict[str, Any]
    enabled: bool


def _load_entries() -> list[RegistryEntry]:
    if not REGISTRY_PATH.exists():
        return []
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    entries_raw = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(entries_raw, list):
        return []

    entries: list[RegistryEntry] = []
    for item in entries_raw:
        if not isinstance(item, dict):
            continue
        key = clean_text(item.get("key", ""))
        org_name = clean_text(item.get("org_name", ""))
        if not key or not org_name:
            continue
        selectors = item.get("selectors") if isinstance(item.get("selectors"), dict) else {}
        entries.append(
            RegistryEntry(
                key=key,
                org_name=org_name,
                prefecture=clean_text(item.get("prefecture", "")),
                url=clean_text(item.get("url", "")),
                parser_type=clean_text(item.get("parser_type", "table_utils")) or "table_utils",
                category_hint=clean_text(item.get("category_hint", "")),
                external_use=clean_text(item.get("external_use", "")),
                selectors=selectors,
                enabled=bool(item.get("enabled", True)),
            )
        )
    return entries


def fetch_registry_low_count_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    records: list[RawEquipment] = []
    for entry in _load_entries():
        if not entry.enabled:
            continue
        if entry.parser_type not in {"table_utils", "table"}:
            continue
        if not entry.url:
            continue

        selectors = entry.selectors or {}
        link_patterns = selectors.get("link_patterns", [])
        required_table_links = selectors.get("required_table_links", [])
        config = TableConfig(
            key=entry.key,
            org_name=entry.org_name,
            url=entry.url,
            org_type=clean_text(selectors.get("org_type", "")),
            category_hint=entry.category_hint,
            external_use=entry.external_use,
            link_patterns=tuple(link_patterns if isinstance(link_patterns, list) else []),
            required_table_links=tuple(
                required_table_links if isinstance(required_table_links, list) else []
            ),
            force_apparent_encoding=bool(selectors.get("force_apparent_encoding", False)),
        )

        remaining = 0 if limit == 0 else max(limit - len(records), 0)
        for raw in fetch_table_records(config=config, timeout=timeout, limit=remaining):
            records.append(
                RawEquipment(
                    equipment_id=raw.equipment_id,
                    name=raw.name,
                    category=raw.category,
                    category_general=raw.category_general,
                    category_detail=raw.category_detail,
                    org_name=raw.org_name or entry.org_name,
                    org_type=raw.org_type,
                    prefecture=raw.prefecture or entry.prefecture,
                    address_raw=raw.address_raw or entry.org_name,
                    lat=raw.lat,
                    lng=raw.lng,
                    external_use=raw.external_use or entry.external_use,
                    fee_note=raw.fee_note,
                    conditions_note=raw.conditions_note,
                    source_url=raw.source_url or entry.url,
                    source_updated_at=raw.source_updated_at,
                )
            )
            if limit and len(records) >= limit:
                return records

    return records
