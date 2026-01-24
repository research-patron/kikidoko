from __future__ import annotations

import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.shinshu-u.ac.jp/institution/kiban/kiki/secchi/"
ORG_NAME = "信州大学 基盤研究支援センター 機器分析支援部門"
PREFECTURE = "長野県"
CATEGORY_GENERAL = "研究設備"


def fetch_shinshu_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    records: list[RawEquipment] = []
    seen: set[str] = set()
    for table in soup.select("table.boxKikiEquipment"):
        name = _cell_text(table.select_one("p.name"))
        if not name:
            continue
        model = _cell_text(table.select_one("p.spec"))
        location = _extract_location(table)
        category_detail = _find_category(table)

        equipment_id = _build_equipment_id(name, model, category_detail)
        dedupe_key = equipment_id or f"{name}|{model}|{location}|{category_detail}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        records.append(
            RawEquipment(
                equipment_id=equipment_id,
                name=name,
                category_general=CATEGORY_GENERAL,
                category_detail=category_detail,
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw=location,
        conditions_note=_build_conditions_note(model),
                source_url=LIST_URL,
            )
        )
        if limit and len(records) >= limit:
            return records

    return records


def _cell_text(element: BeautifulSoup | None) -> str:
    if not element:
        return ""
    return clean_text(element.get_text(" ", strip=True))


def _extract_location(table: BeautifulSoup) -> str:
    rows = table.select("tbody tr")
    if len(rows) >= 2:
        return clean_text(rows[1].get_text(" ", strip=True))
    if rows:
        return clean_text(rows[-1].get_text(" ", strip=True))
    return ""


def _find_category(table: BeautifulSoup) -> str:
    for heading in table.find_all_previous(["h2", "h3", "h4"], limit=6):
        text = clean_text(heading.get_text(" ", strip=True))
        if text:
            return text
    return ""


def _build_conditions_note(model: str) -> str:
    if not model:
        return ""
    return f"機種: {model}"


def _build_equipment_id(name: str, model: str, category: str) -> str:
    base = clean_text("|".join([name, model, category]))
    if not base:
        return ""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", base).strip("-")
    return f"SHINSHU-{slug}" if slug else ""
