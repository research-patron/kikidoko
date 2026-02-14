from __future__ import annotations

from itertools import zip_longest

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.chem.nara-wu.ac.jp/chemguide/equipment.html"
ORG_NAME = "奈良女子大学 理学部 化学コース"
PREFECTURE = "奈良県"
CATEGORY_GENERAL = "共用機器"


def fetch_nara_wu_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    head_tables = soup.select("table.equipment_name")
    detail_tables = [table for table in soup.select("table") if "equipment_name" not in table.get("class", [])]

    records: list[RawEquipment] = []
    for index, (head_table, detail_table) in enumerate(zip_longest(head_tables, detail_tables), start=1):
        if head_table is None:
            continue
        head_map = _table_to_map(head_table)
        detail_map = _table_to_map(detail_table) if detail_table else {}

        name = head_map.get("装置名称", "") or head_map.get("装置種類", "")
        name = clean_text(name)
        if not name:
            continue

        equipment_type = clean_text(head_map.get("装置種類", ""))
        location = clean_text(detail_map.get("設置場所", ""))
        conditions_note = _build_conditions_note(detail_map)
        fee_note = clean_text(detail_map.get("利用料金", ""))

        records.append(
            RawEquipment(
                equipment_id=f"NARA-WU-{index:03d}",
                name=name,
                category_general=CATEGORY_GENERAL,
                category_detail=equipment_type,
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw=location or ORG_NAME,
                external_use="不可",
                fee_note=_truncate(fee_note, 280),
                conditions_note=_truncate(conditions_note, 1200),
                source_url=LIST_URL,
            )
        )
        if limit and len(records) >= limit:
            return records

    return records


def _table_to_map(table: BeautifulSoup | None) -> dict[str, str]:
    if table is None:
        return {}
    result: dict[str, str] = {}
    for row in table.select("tr"):
        key_cell = row.find("th")
        value_cell = row.find("td")
        if not key_cell or not value_cell:
            continue
        key = clean_text(key_cell.get_text(" ", strip=True))
        value = clean_text(value_cell.get_text(" ", strip=True))
        if key and value:
            result[key] = value
    return result


def _build_conditions_note(detail_map: dict[str, str]) -> str:
    order = ["導入年度", "特徴", "使用条件", "管理責任者", "問合せ先"]
    parts: list[str] = []
    for key in order:
        value = clean_text(detail_map.get(key, ""))
        if value:
            parts.append(f"{key}: {value}")
    return " / ".join(parts)


def _truncate(value: str, max_len: int) -> str:
    value = clean_text(value)
    if len(value) <= max_len:
        return value
    return f"{value[: max_len - 1]}…"
