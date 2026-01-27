from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class RawEquipment:
    equipment_id: str = ""
    name: str = ""
    category: str = ""
    category_general: str = ""
    category_detail: str = ""
    org_name: str = ""
    org_type: str = ""
    prefecture: str = ""
    address_raw: str = ""
    lat: float | None = None
    lng: float | None = None
    external_use: str = ""
    fee_note: str = ""
    conditions_note: str = ""
    source_url: str = ""
    source_updated_at: str = ""


@dataclass
class EquipmentRecord:
    equipment_id: str = ""
    name: str = ""
    category_general: str = ""
    category_detail: str = ""
    org_name: str = ""
    org_type: str = ""
    prefecture: str = ""
    region: str = ""
    address_raw: str = ""
    lat: float | None = None
    lng: float | None = None
    external_use: str = ""
    fee_band: str = ""
    fee_note: str = ""
    conditions_note: str = ""
    source_url: str = ""
    crawled_at: str = ""
    source_updated_at: str = ""
    dedupe_key: str = ""
    search_tokens: list[str] | None = None
    search_aliases: list[str] | None = None

    def to_firestore(self) -> dict[str, Any]:
        data = asdict(self)
        return {key: value for key, value in data.items() if value not in ("", None)}
