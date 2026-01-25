from __future__ import annotations

import hashlib
import re

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.kagawa-u.ac.jp/nanoplatform/equipment.html"
ORG_NAME = "香川大学 微細加工プラットフォーム"
PREFECTURE = "香川県"
CATEGORY_GENERAL = "微細加工プラットフォーム"


def fetch_kagawa_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    records: list[RawEquipment] = []
    seen: set[str] = set()
    handled_tables: set[int] = set()

    for heading in soup.find_all("h3"):
        category_detail = clean_text(heading.get_text(" ", strip=True))
        table = heading.find_next("table")
        if not table or id(table) in handled_tables:
            continue
        handled_tables.add(id(table))
        if not _is_equipment_table(table):
            continue

        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            name = clean_text(cells[0].get_text(" ", strip=True))
            detail = clean_text(cells[1].get_text(" ", strip=True))
            if not name:
                continue

            equipment_id = _build_equipment_id(name)
            if equipment_id in seen:
                continue
            seen.add(equipment_id)

            records.append(
                RawEquipment(
                    equipment_id=equipment_id,
                    name=name,
                    category_general=CATEGORY_GENERAL,
                    category_detail=category_detail,
                    org_name=ORG_NAME,
                    prefecture=PREFECTURE,
                    address_raw="香川大学",
                    conditions_note=_build_conditions_note(detail),
                    source_url=LIST_URL,
                )
            )
            if limit and len(records) >= limit:
                return records

    return records


def _is_equipment_table(table: BeautifulSoup) -> bool:
    headers = [clean_text(cell.get_text(" ", strip=True)) for cell in table.find_all("th")]
    return any(header == "装置名" for header in headers)


def _build_equipment_id(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", clean_text(name)).strip("-")
    if slug:
        return f"KAGAWA-{slug}"
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
    return f"KAGAWA-{digest}"


def _build_conditions_note(detail: str) -> str:
    return f"詳細: {detail}" if detail else ""
