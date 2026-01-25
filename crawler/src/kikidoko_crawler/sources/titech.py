from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://kyoyo.rpd.titech.ac.jp/search/?mode=search"
DETAIL_PATH = "/search/data/public/detail/"
ORG_NAME = "東京工業大学"
PREFECTURE = "東京都"
FALLBACK_CATEGORY = "共用設備"


def fetch_titech_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.select_one("#js-resultTable")
    if not table:
        return []

    records: list[RawEquipment] = []
    for row in table.select("tbody tr"):
        record = _extract_row(row)
        if not record:
            continue
        records.append(record)
        if limit and len(records) >= limit:
            return records

    return records


def _extract_row(row: BeautifulSoup) -> RawEquipment | None:
    cells = row.find_all(["th", "td"])
    if not cells:
        return None

    name_cell = cells[0]
    name = clean_text(name_cell.get_text(" ", strip=True))
    if not name:
        return None

    detail_url = _extract_detail_url(name_cell)
    equipment_id = _format_equipment_id(_extract_id_from_url(detail_url))
    maker = _cell_text(cells, 1)
    model = _cell_text(cells, 2)
    category_general, category_detail = _split_category(_cell_lines(cells, 3))
    affiliation = " ".join(_cell_lines(cells, 4))
    self_use = _cell_text(cells, 5)
    request_use = _cell_text(cells, 6)
    contact_url = _extract_contact_url(cells, 7)

    external_use = _normalize_external_use(self_use, request_use)
    conditions_note = _build_conditions_note(maker, model, contact_url)

    return RawEquipment(
        equipment_id=equipment_id,
        name=name,
        category_general=category_general or FALLBACK_CATEGORY,
        category_detail=category_detail,
        org_name=ORG_NAME,
        prefecture=PREFECTURE,
        address_raw=affiliation,
        external_use=external_use,
        conditions_note=conditions_note,
        source_url=detail_url or LIST_URL,
    )


def _cell_text(cells: list[BeautifulSoup], index: int) -> str:
    if index < 0 or index >= len(cells):
        return ""
    return clean_text(cells[index].get_text(" ", strip=True))


def _cell_lines(cells: list[BeautifulSoup], index: int) -> list[str]:
    if index < 0 or index >= len(cells):
        return []
    text = cells[index].get_text("\n", strip=True)
    lines = [clean_text(line) for line in text.split("\n")]
    return [line for line in lines if line]


def _extract_detail_url(cell: BeautifulSoup) -> str:
    anchor = cell.find("a", href=True)
    if not anchor:
        return ""
    href = anchor.get("href", "")
    if DETAIL_PATH not in href:
        return ""
    return urljoin(LIST_URL, href)


def _extract_contact_url(cells: list[BeautifulSoup], index: int) -> str:
    if index < 0 or index >= len(cells):
        return ""
    anchor = cells[index].find("a", href=True)
    if not anchor:
        return ""
    return urljoin(LIST_URL, anchor["href"])


def _extract_id_from_url(url: str) -> str:
    match = re.search(r"/detail/(\\d+)", url or "")
    return match.group(1) if match else ""


def _format_equipment_id(raw_id: str) -> str:
    if not raw_id:
        return ""
    return f"TITECH-{raw_id}"


def _split_category(values: list[str]) -> tuple[str, str]:
    if not values:
        return "", ""
    if len(values) == 1:
        return values[0], ""
    return values[0], " / ".join(values[1:])


def _normalize_external_use(*values: str) -> str:
    text = " ".join([clean_text(value) for value in values if value])
    if not text:
        return ""
    if "不可" in text:
        return "不可"
    if "応相談" in text or "要相談" in text:
        return "要相談"
    if "学外" in text or "学内外" in text:
        return "可"
    if "学内" in text:
        return "不可"
    return ""


def _build_conditions_note(maker: str, model: str, contact_url: str) -> str:
    parts: list[str] = []
    if maker:
        parts.append(f"メーカー: {maker}")
    if model:
        parts.append(f"型番: {model}")
    if contact_url:
        parts.append(f"問い合わせ先: {contact_url}")
    return " / ".join(parts)
