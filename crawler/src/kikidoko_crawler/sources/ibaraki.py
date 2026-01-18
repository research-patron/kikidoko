from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.ofc.ibaraki.ac.jp/facility"
ORG_NAME = "茨城大学 研究設備共用センター"
PREFECTURE = "茨城県"


def fetch_ibaraki_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")
    content = soup.find("main") or soup

    records: list[RawEquipment] = []
    current_category = ""
    for node in content.find_all(["h2", "table"]):
        if node.name == "h2":
            current_category = clean_text(node.get_text(" ", strip=True))
            continue
        records.extend(_extract_table_records(node, current_category))
        if limit and len(records) >= limit:
            return records[:limit]

    return records


def _extract_table_records(table: BeautifulSoup, category: str) -> list[RawEquipment]:
    rows = table.find_all("tr")
    if not rows:
        return []
    headers = [clean_text(cell.get_text(" ", strip=True)) for cell in rows[0].find_all(["th", "td"])]
    if "機器名" not in headers:
        return []

    records: list[RawEquipment] = []
    for row in rows[1:]:
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all("td")]
        if not cells:
            continue
        row_data = _map_row(headers, cells)
        name = row_data.get("機器名", "")
        if not name:
            continue
        address_raw = _build_address(row_data)
        conditions_note = _build_conditions_note(row_data)

        records.append(
            RawEquipment(
                name=name,
                category_general=category,
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw=address_raw,
                conditions_note=conditions_note,
                source_url=LIST_URL,
            )
        )
    return records


def _map_row(headers: list[str], cells: list[str]) -> dict[str, str]:
    data: dict[str, str] = {}
    for index, header in enumerate(headers):
        data[header] = cells[index] if index < len(cells) else ""
    return data


def _build_address(data: dict[str, str]) -> str:
    location = data.get("設置場所", "")
    if location:
        return f"茨城大学 {location}"
    return "茨城大学"


def _build_conditions_note(data: dict[str, str]) -> str:
    notes: list[str] = []
    abbr = data.get("略称", "")
    if abbr and abbr not in {"-", "－"}:
        notes.append(f"略称: {abbr}")
    maker = data.get("メーカー名・型式", "")
    if maker:
        notes.append(f"メーカー・型式: {maker}")
    managing = data.get("管理部局", "")
    if managing:
        notes.append(f"管理部局: {managing}")
    return " / ".join(notes)
