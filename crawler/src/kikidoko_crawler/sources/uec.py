from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

BASE_URL = "http://www.cia.uec.ac.jp/hp"
API_URL = "http://www.cia.uec.ac.jp/hp/wp-json/wp/v2/posts"
CATEGORY_ID = 5
ORG_NAME = "電気通信大学 研究設備センター 基盤研究設備部門"
PREFECTURE = "東京都"
CATEGORY_GENERAL = "基盤研究設備部門"


def fetch_uec_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    session = requests.Session()
    records: list[RawEquipment] = []
    seen: set[int] = set()

    page = 1
    total_pages = 1
    while page <= total_pages:
        params = {"categories": str(CATEGORY_ID), "per_page": "100", "page": str(page)}
        response = session.get(API_URL, params=params, timeout=timeout)
        response.raise_for_status()
        total_pages = int(response.headers.get("X-WP-TotalPages", "1"))
        items = response.json()

        for item in items:
            post_id = item.get("id")
            if post_id in seen:
                continue
            seen.add(post_id)
            record = _build_record(item)
            if not record:
                continue
            records.append(record)
            if limit and len(records) >= limit:
                return records

        page += 1

    return records


def _build_record(item: dict[str, object]) -> RawEquipment | None:
    title_html = (item.get("title") or {}).get("rendered", "")
    title = clean_text(BeautifulSoup(str(title_html), "html.parser").get_text(" ", strip=True))
    if not title:
        return None

    content_html = (item.get("content") or {}).get("rendered", "")
    maker, model, manager, department, location = _extract_details(str(content_html))
    equipment_id = _format_equipment_id(str(item.get("id", "")))
    source_url = str(item.get("link", ""))

    conditions_note = _join_notes(
        _format_note("メーカー", maker),
        _format_note("型番", model),
        _format_note("管理責任者", manager),
        department,
    )

    return RawEquipment(
        equipment_id=equipment_id,
        name=title,
        category_general=CATEGORY_GENERAL,
        org_name=ORG_NAME,
        prefecture=PREFECTURE,
        address_raw=_format_address(location),
        conditions_note=conditions_note,
        source_url=source_url,
    )


def _extract_details(html: str) -> tuple[str, str, str, str, str]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table:
        return _extract_from_table(table)
    return _extract_from_text(soup.get_text("\n", strip=True))


def _extract_from_table(table: BeautifulSoup) -> tuple[str, str, str, str, str]:
    maker = ""
    model = ""
    manager = ""
    department = ""
    location = ""

    row = table.find("tr")
    if row:
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
        cells = [cell for cell in cells if cell]
        for idx, cell in enumerate(cells):
            if "管理責任者" in cell and idx + 1 < len(cells):
                manager = cells[idx + 1]
                if idx + 2 < len(cells) and _is_detail_value(cells[idx + 2]):
                    department = cells[idx + 2]
            if "設置場所" in cell and idx + 1 < len(cells):
                location = cells[idx + 1]
        if cells:
            label_indices = [
                idx
                for idx, cell in enumerate(cells)
                if "管理責任者" in cell or "設置場所" in cell
            ]
            first_label = min(label_indices) if label_indices else len(cells)
            if first_label >= 2:
                maker = cells[0]
                model = cells[1]
            elif first_label == 1:
                maker = cells[0]

    return maker, model, manager, department, location


def _extract_from_text(text: str) -> tuple[str, str, str, str, str]:
    lines = [clean_text(line) for line in text.split("\n") if clean_text(line)]
    maker = ""
    model = ""
    manager = ""
    department = ""
    location = ""

    if "管理責任者：" in lines:
        idx = lines.index("管理責任者：")
        if idx >= 2:
            maker = lines[0]
            model = lines[1]
        if idx + 1 < len(lines):
            manager = lines[idx + 1]
        if idx + 2 < len(lines) and "設置場所" not in lines[idx + 2]:
            department = lines[idx + 2]
    if "設置場所：" in lines:
        idx = lines.index("設置場所：")
        if idx + 1 < len(lines):
            location = lines[idx + 1]

    return maker, model, manager, department, location


def _format_address(location: str) -> str:
    location = clean_text(location)
    if not location:
        return ""
    return f"電気通信大学 {location}"


def _format_equipment_id(raw_id: str) -> str:
    raw_id = clean_text(raw_id)
    if not raw_id:
        return ""
    return f"UEC-{raw_id}"


def _format_note(label: str, value: str) -> str:
    value = clean_text(value)
    if not value:
        return ""
    return f"{label}: {value}"


def _join_notes(*notes: str) -> str:
    cleaned = [clean_text(note) for note in notes if clean_text(note)]
    return " / ".join(cleaned)


def _is_detail_value(value: str) -> bool:
    return not any(key in value for key in ("管理責任者", "設置場所"))
