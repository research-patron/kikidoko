from __future__ import annotations

import re
import warnings

import requests
from bs4 import BeautifulSoup
from urllib3.exceptions import InsecureRequestWarning

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.opf.osaka-u.ac.jp/instruments/list"
DETAIL_URL_PREFIX = "https://www.opf.osaka-u.ac.jp/instruments/"
ORG_NAME = "大阪大学 コアファシリティ機構 研究設備・機器共通予約システム"
PREFECTURE = "大阪府"


def fetch_osaka_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    warnings.filterwarnings("ignore", category=InsecureRequestWarning)

    response = requests.get(LIST_URL, timeout=timeout, verify=False)
    response.raise_for_status()
    payload = response.json()

    records: list[RawEquipment] = []
    for item in payload.get("Records", []):
        if item.get("del_flag") not in ("0", None, ""):
            continue
        name = _build_name(item)
        if not name:
            continue
        categories = _split_categories(item.get("category_names", ""))
        category_general = categories[0] if categories else ""
        category_detail = " / ".join(categories[1:]) if len(categories) > 1 else ""
        external_use = "可" if str(item.get("gov_show")) == "1" else "不可"
        records.append(
            RawEquipment(
                equipment_id=_build_equipment_id(item),
                name=name,
                category_general=category_general,
                category_detail=category_detail,
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw=_build_address(item),
                external_use=external_use,
                conditions_note=_build_conditions_note(item),
                source_url=_build_source_url(item),
                source_updated_at=clean_text(item.get("update_date", "")),
            )
        )
        if limit and len(records) >= limit:
            return records

    return records


def _build_name(item: dict) -> str:
    name = clean_text(item.get("item_name", ""))
    eng = clean_text(item.get("item_name_eng", ""))
    if eng and eng not in name:
        name = f"{name} ({eng})"
    return name


def _split_categories(raw: str) -> list[str]:
    if not raw:
        return []
    parts = re.split(r"[、,]", clean_text(raw))
    categories: list[str] = []
    for part in parts:
        cleaned = re.sub(r"^\d+\.?\s*", "", part).strip()
        if cleaned:
            categories.append(cleaned)
    return categories


def _build_conditions_note(item: dict) -> str:
    parts: list[str] = []
    maker = clean_text(item.get("maker", ""))
    type_no = clean_text(item.get("type_no", ""))
    owner = clean_text(item.get("apparatus_owner", ""))
    department = clean_text(item.get("department_name", ""))
    performance = _html_to_text(item.get("performance", ""))
    notes = _html_to_text(item.get("notes", ""))
    if maker:
        parts.append(f"メーカー: {maker}")
    if type_no:
        parts.append(f"型番: {type_no}")
    if department:
        parts.append(f"部局: {department}")
    if owner:
        parts.append(f"管理者: {owner}")
    if performance:
        parts.append(f"性能: {performance}")
    if notes:
        parts.append(f"備考: {notes}")
    return " / ".join(parts)


def _html_to_text(value: str) -> str:
    text = clean_text(value)
    if not text or "<" not in text:
        return text
    soup = BeautifulSoup(text, "html.parser")
    return clean_text(soup.get_text(" ", strip=True))


def _build_address(item: dict) -> str:
    parts = ["大阪大学"]
    department = clean_text(item.get("department_name", ""))
    location = clean_text(item.get("location_etc", ""))
    if department:
        parts.append(department)
    if location:
        parts.append(location)
    return " ".join(parts)


def _build_source_url(item: dict) -> str:
    item_id = clean_text(item.get("item_id", ""))
    if item_id:
        return f"{DETAIL_URL_PREFIX}{item_id}"
    return LIST_URL


def _build_equipment_id(item: dict) -> str:
    item_id = clean_text(item.get("item_id", ""))
    if not item_id:
        return ""
    return f"OSAKA-{item_id}"
