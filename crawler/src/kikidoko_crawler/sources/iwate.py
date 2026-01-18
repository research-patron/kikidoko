from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = (
    "https://iwa-kiki.ccrd.iwate-u.ac.jp/"
    "%E6%A9%9F%E5%99%A8%E3%83%87%E3%83%BC%E3%82%BF%E3%83%99%E3%83%BC%E3%82%B9/"
)
ORG_NAME = "岩手大学 全学共同利用機器"
PREFECTURE = "岩手県"


def fetch_iwate_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")
    content = soup.find("article") or soup

    records: list[RawEquipment] = []
    current_category = ""
    for node in content.find_all(["h2", "table"]):
        if node.name == "h2":
            current_category = clean_text(node.get_text(" ", strip=True))
            continue
        record = _extract_table_record(node, current_category)
        if not record:
            continue
        records.append(record)
        if limit and len(records) >= limit:
            return records

    return records


def _extract_table_record(table: BeautifulSoup, category: str) -> RawEquipment | None:
    row = table.find("tr")
    if not row:
        return None
    cells = row.find_all("td")
    if len(cells) < 2:
        return None

    labels = _split_lines(cells[0])
    values = _split_lines(cells[1])
    if not labels or not values:
        return None
    data = {label: values[index] if index < len(values) else "" for index, label in enumerate(labels)}

    model = data.get("型式", "")
    name = _build_name(category, model)
    if not name:
        return None

    maker = data.get("製造メーカー", "")
    location = data.get("設置場所", "")
    year = data.get("設置年度", "")
    spec = data.get("性能", "")
    spec_note = data.get("仕様", "")
    contact = data.get("問合せ先", "")

    notes: list[str] = []
    if maker:
        notes.append(f"メーカー: {maker}")
    if year:
        notes.append(f"設置年度: {year}")
    if spec:
        notes.append(f"性能: {spec}")
    if spec_note:
        notes.append(f"仕様: {spec_note}")
    if contact:
        notes.append(f"問合せ先: {contact}")

    address_raw = f"岩手大学 {location}" if location else "岩手大学"

    return RawEquipment(
        name=name,
        category_general=category,
        org_name=ORG_NAME,
        prefecture=PREFECTURE,
        address_raw=address_raw,
        conditions_note=" / ".join(notes),
        source_url=LIST_URL,
    )


def _split_lines(cell: BeautifulSoup) -> list[str]:
    return [clean_text(text) for text in cell.stripped_strings if clean_text(text)]


def _build_name(category: str, model: str) -> str:
    if category and model:
        return f"{category} ({model})"
    return model or category
