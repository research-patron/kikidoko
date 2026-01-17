from __future__ import annotations

from datetime import datetime, timezone

from .models import EquipmentRecord, RawEquipment
from .utils import (
    classify_external_use,
    classify_fee_band,
    compute_dedupe_key,
    guess_prefecture,
    parse_date,
)


def split_category(category: str) -> tuple[str, str]:
    if not category:
        return "", ""
    for sep in (">", "＞", "/", "／"):
        if sep in category:
            parts = [item.strip() for item in category.split(sep) if item.strip()]
            if parts:
                general = parts[0]
                detail = parts[1] if len(parts) > 1 else ""
                return general, detail
    return category.strip(), ""


def classify_org_type(org_name: str) -> str:
    if not org_name:
        return "不明"
    if "高専" in org_name or "高等専門学校" in org_name:
        return "高等専門学校"
    if "国立" in org_name and "大学" in org_name:
        return "国立大学"
    if "公立" in org_name and "大学" in org_name:
        return "公立大学"
    if "私立" in org_name and "大学" in org_name:
        return "私立大学"
    if "学校法人" in org_name:
        return "私立大学"
    if "大学" in org_name:
        return "国立大学"
    if "研究所" in org_name or "研究機構" in org_name or "研究センター" in org_name:
        return "公的研究機関"
    return "不明"


def normalize_equipment(raw: RawEquipment) -> EquipmentRecord:
    category_general = raw.category_general
    category_detail = raw.category_detail
    if not category_general:
        category_general, category_detail = split_category(raw.category)

    org_type = raw.org_type or classify_org_type(raw.org_name)
    prefecture = raw.prefecture or guess_prefecture(raw.address_raw or raw.org_name)
    external_use = classify_external_use(raw.external_use)
    fee_band = classify_fee_band(raw.fee_note)
    source_updated_at = parse_date(raw.source_updated_at)
    crawled_at = datetime.now(timezone.utc).isoformat()
    dedupe_key = compute_dedupe_key(raw.org_name, raw.name, category_general)

    return EquipmentRecord(
        equipment_id=raw.equipment_id,
        name=raw.name,
        category_general=category_general,
        category_detail=category_detail,
        org_name=raw.org_name,
        org_type=org_type,
        prefecture=prefecture,
        address_raw=raw.address_raw,
        external_use=external_use,
        fee_band=fee_band,
        fee_note=raw.fee_note,
        conditions_note=raw.conditions_note,
        source_url=raw.source_url,
        crawled_at=crawled_at,
        source_updated_at=source_updated_at,
        dedupe_key=dedupe_key,
    )
