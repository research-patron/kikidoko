from __future__ import annotations

import math
import re
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from ..models import RawEquipment
from ..utils import clean_text

BASE_URL = "https://univ.obihiro.ac.jp/~kyotuportal/basic/web/index.php"
LIST_URL = f"{BASE_URL}?r=site%2Findex&dp-1-sort=title"
ORG_NAME = "帯広畜産大学 産学連携センター 共同利用設備ステーション"
PREFECTURE = "北海道"
CATEGORY_GENERAL = "共同利用設備ステーション"


def fetch_obihiro_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    session = requests.Session()
    first_page = _fetch_page(session, LIST_URL, timeout)
    if not first_page:
        return []

    max_page = _discover_max_page(first_page)
    records: list[RawEquipment] = []

    for page in range(1, max_page + 1):
        page_url = _build_page_url(page)
        soup = first_page if page == 1 else _fetch_page(session, page_url, timeout)
        if not soup:
            continue

        for record in _extract_page_records(soup):
            records.append(record)
            if limit and len(records) >= limit:
                return records

    return records


def _fetch_page(
    session: requests.Session, url: str, timeout: int
) -> BeautifulSoup | None:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return BeautifulSoup(response.text, "html.parser")


def _discover_max_page(soup: BeautifulSoup) -> int:
    total = _extract_total_count(soup)
    page_size = _extract_page_size(soup)
    if total and page_size:
        return max(1, math.ceil(total / page_size))

    max_page = 1
    for anchor in soup.select("ul.pagination a[href]"):
        page = _extract_page_number(anchor.get("href", ""))
        if page:
            max_page = max(max_page, page)
    return max_page


def _extract_page_number(href: str) -> int:
    if not href:
        return 0
    parsed = urlparse(href)
    query = parse_qs(parsed.query)
    page_values = query.get("page", [])
    if not page_values:
        return 0
    value = page_values[0]
    return int(value) if value.isdigit() else 0


def _extract_total_count(soup: BeautifulSoup) -> int:
    for summary in soup.select("div.summary"):
        text = clean_text(summary.get_text(" ", strip=True))
        if not text:
            continue
        match = re.search(r"(\d+)\s*件中", text)
        if match:
            return int(match.group(1))
    return 0


def _extract_page_size(soup: BeautifulSoup) -> int:
    grid = soup.select_one("table.kv-grid-table")
    if not grid:
        return 0
    rows = grid.find_all("tr")[1:]
    return len(rows)


def _build_page_url(page: int) -> str:
    if page <= 1:
        return LIST_URL
    return f"{LIST_URL}&page={page}&per-page=10"


def _extract_page_records(soup: BeautifulSoup) -> list[RawEquipment]:
    grid = soup.select_one("table.kv-grid-table")
    if not grid:
        return []
    records: list[RawEquipment] = []
    for row in grid.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 7:
            continue
        name_cell = cells[1]
        name = clean_text(name_cell.get_text(" ", strip=True))
        if not name:
            continue
        category_detail = clean_text(cells[2].get_text(" ", strip=True))
        model = clean_text(cells[3].get_text(" ", strip=True))
        detail = clean_text(cells[4].get_text(" ", strip=True))
        location = clean_text(cells[5].get_text(" ", strip=True))
        manager = clean_text(cells[6].get_text(" ", strip=True))
        source_url = _normalize_detail_url(_extract_link(name_cell))
        equipment_id = _build_equipment_id(source_url)
        conditions_note = _build_conditions_note(model, detail, manager)

        records.append(
            RawEquipment(
                equipment_id=equipment_id,
                name=name,
                category_general=CATEGORY_GENERAL,
                category_detail=category_detail,
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw=_build_address(location),
                external_use="要相談",
                conditions_note=conditions_note,
                source_url=source_url or LIST_URL,
            )
        )
    return records


def _extract_link(cell: Tag) -> str:
    anchor = cell.find("a", href=True)
    return anchor["href"] if anchor else ""


def _normalize_detail_url(href: str) -> str:
    if not href:
        return ""
    resolved = urljoin(LIST_URL, href)
    if "board.obihiro.ac.jp" in resolved:
        equipment_id = _extract_id(resolved)
        if equipment_id:
            return f"{BASE_URL}?r=device%2Fview_user&id={equipment_id}"
    return resolved


def _extract_id(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    return query.get("id", [""])[0]


def _build_equipment_id(source_url: str) -> str:
    if not source_url:
        return ""
    equipment_id = _extract_id(source_url)
    if equipment_id:
        return f"OBIHIRO-{equipment_id}"
    return ""


def _build_conditions_note(model: str, detail: str, manager: str) -> str:
    parts: list[str] = []
    if model and model != "-":
        parts.append(f"型式: {model}")
    if detail and detail != "-":
        parts.append(f"説明: {detail}")
    if manager:
        parts.append(f"管理責任者: {manager}")
    return " / ".join(parts)


def _build_address(location: str) -> str:
    if not location:
        return "帯広畜産大学"
    if "帯広" in location or "大学" in location:
        return location
    return f"帯広畜産大学 {location}"
