from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.jaist.ac.jp/project/arim/equipment/"
ORG_NAME = "北陸先端科学技術大学院大学 ナノマテリアルテクノロジーセンター"
PREFECTURE = "石川県"


def fetch_jaist_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
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
        record = _extract_record(node, current_category)
        if not record:
            continue
        records.append(record)
        if limit and len(records) >= limit:
            return records

    return records


def _extract_record(table: BeautifulSoup, category: str) -> RawEquipment | None:
    rows = table.find_all("tr")
    if not rows:
        return None

    data: dict[str, str] = {}
    for row in rows:
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
        if len(cells) < 2:
            continue
        data[cells[0]] = cells[1]

    equipment_id = data.get("装置ID", "")
    model = data.get("製造メーカ名・型番", "")
    name = model or equipment_id
    if not name:
        return None

    notes: list[str] = []
    for key in ("利用状況", "詳細", "担当者"):
        value = data.get(key, "")
        if value:
            notes.append(f"{key}: {value}")

    return RawEquipment(
        equipment_id=f"JAIST-{equipment_id}" if equipment_id else "",
        name=name,
        category_general=category,
        org_name=ORG_NAME,
        prefecture=PREFECTURE,
        address_raw="北陸先端科学技術大学院大学",
        conditions_note=" / ".join(notes),
        source_url=LIST_URL,
    )
