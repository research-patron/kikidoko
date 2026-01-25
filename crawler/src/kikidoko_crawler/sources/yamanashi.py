from __future__ import annotations

import hashlib
import re

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text, normalize_label

LIST_URL = "https://clab.yamanashi.ac.jp/list/"
ORG_NAME = "山梨大学 機器分析センター"
PREFECTURE = "山梨県"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def fetch_yamanashi_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    session = requests.Session()
    session.headers.update(HEADERS)
    response = session.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.find("table")
    if not table:
        return []

    rows = table.find_all("tr")
    if not rows:
        return []

    headers = [clean_text(cell.get_text(" ", strip=True)) for cell in rows[0].find_all(["th", "td"])]
    mapping = {normalize_label(label): idx for idx, label in enumerate(headers)}

    records: list[RawEquipment] = []
    seen: set[str] = set()
    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        if not cells:
            continue

        name = _cell_text(cells, mapping, "機器名", 0)
        if not name:
            continue
        alias = _cell_text(cells, mapping, "略称・通称", 1)
        maker = _cell_text(cells, mapping, "メーカー", 2)
        model = _cell_text(cells, mapping, "機種名・型番", 3)
        field1 = _cell_text(cells, mapping, "分野1", 4)
        field2 = _cell_text(cells, mapping, "分野2", 5)

        equipment_id = _build_equipment_id(name, alias, model)
        if equipment_id and equipment_id in seen:
            continue
        if equipment_id:
            seen.add(equipment_id)

        records.append(
            RawEquipment(
                equipment_id=equipment_id,
                name=name,
                category_general=field1,
                category_detail=field2,
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw=ORG_NAME,
                conditions_note=_build_conditions_note(alias, maker, model),
                source_url=LIST_URL,
            )
        )
        if limit and len(records) >= limit:
            return records

    return records


def _cell_text(
    cells: list[BeautifulSoup], mapping: dict[str, int], label: str, fallback: int
) -> str:
    index = mapping.get(normalize_label(label), fallback)
    if index < 0 or index >= len(cells):
        return ""
    return clean_text(cells[index].get_text(" ", strip=True))


def _build_equipment_id(name: str, alias: str, model: str) -> str:
    base = alias or name
    slug = re.sub(r"[^A-Za-z0-9]+", "-", clean_text(base)).strip("-")
    model_slug = re.sub(r"[^A-Za-z0-9]+", "-", clean_text(model)).strip("-")
    if slug and model_slug:
        return f"YAMANASHI-{slug.upper()}-{model_slug.upper()}"
    if slug:
        return f"YAMANASHI-{slug.upper()}"
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
    return f"YAMANASHI-{digest}"


def _build_conditions_note(alias: str, maker: str, model: str) -> str:
    parts: list[str] = []
    if alias:
        parts.append(f"略称: {alias}")
    if maker:
        parts.append(f"メーカー: {maker}")
    if model:
        parts.append(f"型式: {model}")
    return " / ".join(parts)
