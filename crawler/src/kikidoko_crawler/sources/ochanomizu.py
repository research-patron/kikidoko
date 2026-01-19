from __future__ import annotations

import requests
from bs4 import BeautifulSoup, Tag

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.cf.ocha.ac.jp/kikicent/j/menu/equipment/index.html"
ORG_NAME = "お茶の水女子大学 共通機器センター"
PREFECTURE = "東京都"


def fetch_ochanomizu_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")
    content = soup.find("div", id="main_content") or soup

    records: list[RawEquipment] = []
    current_category = ""
    for node in content.find_all(["h2", "table"]):
        if node.name == "h2":
            current_category = clean_text(node.get_text(" ", strip=True))
            continue
        if node.name != "table":
            continue
        records.extend(_extract_table_records(node, current_category, limit, records))
        if limit and len(records) >= limit:
            return records

    return records


def _extract_table_records(
    table: Tag,
    category: str,
    limit: int,
    records: list[RawEquipment],
) -> list[RawEquipment]:
    items: list[RawEquipment] = []
    for row in table.find_all("tr"):
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all("td")]
        if not cells:
            continue
        if "機器名称" in cells[0]:
            continue
        if len(cells) < 6:
            continue
        name = cells[0].lstrip("＊").strip()
        if not name:
            continue
        purchase_year = cells[1]
        unit = cells[2]
        manager = cells[3]
        location = cells[5]
        reserve_url = _extract_reserve_url(row)
        conditions_note = _build_conditions_note(purchase_year, unit, manager, reserve_url)

        items.append(
            RawEquipment(
                name=name,
                category_general=category,
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw=_build_address(location),
                external_use="要相談",
                conditions_note=conditions_note,
                source_url=LIST_URL,
            )
        )

        if limit and len(records) + len(items) >= limit:
            return items

    return items


def _extract_reserve_url(row: Tag) -> str:
    anchor = row.find("a", href=True)
    if not anchor:
        return ""
    href = anchor.get("href", "")
    if not href or href == "予約URL":
        return ""
    return href


def _build_conditions_note(
    purchase_year: str, unit: str, manager: str, reserve_url: str
) -> str:
    parts: list[str] = []
    if purchase_year:
        parts.append(f"購入年度: {purchase_year}")
    if unit:
        parts.append(f"所属: {unit}")
    if manager:
        parts.append(f"管理担当者: {manager}")
    if reserve_url:
        parts.append(f"予約URL: {reserve_url}")
    return " / ".join(parts)


def _build_address(location: str) -> str:
    if not location:
        return "お茶の水女子大学"
    if "お茶" in location or "大学" in location:
        return location
    return f"お茶の水女子大学 {location}"
