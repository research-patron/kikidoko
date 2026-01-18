from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.t.kyoto-u.ac.jp/ja/research/yui/list"
ORG_NAME = "京都大学 工学部・大学院工学研究科"
PREFECTURE = "京都府"

ID_PATTERN = re.compile(r"【([^】]+)】")
LOCATION_SKIP = {"料金規程"}


def fetch_kyoto_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")
    content = soup.select_one("#parent-fieldname-text") or soup

    records: list[RawEquipment] = []
    for table in content.find_all("table"):
        category_general = _extract_heading(table)
        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            equipment_id = _extract_equipment_id(cells[0])
            name, detail_url, maker = _extract_name_detail_maker(cells[1])
            if not name:
                continue
            location, campus, fee_note, keywords = _extract_meta(
                cells[2] if len(cells) > 2 else None
            )
            address_raw = _build_address(campus, location)
            conditions_note = _build_conditions_note(maker, keywords)

            records.append(
                RawEquipment(
                    equipment_id=equipment_id,
                    name=name,
                    category_general=category_general,
                    org_name=ORG_NAME,
                    prefecture=PREFECTURE,
                    address_raw=address_raw,
                    fee_note=fee_note,
                    conditions_note=conditions_note,
                    source_url=detail_url or LIST_URL,
                )
            )
            if limit and len(records) >= limit:
                return records

    return records


def _extract_heading(table: BeautifulSoup) -> str:
    heading = table.find_previous(["h3", "h4", "h2"])
    return clean_text(heading.get_text(" ", strip=True)) if heading else ""


def _extract_equipment_id(cell: BeautifulSoup) -> str:
    img = cell.find("img")
    if not img:
        return ""
    title = img.get("title", "")
    match = ID_PATTERN.search(title or "")
    if not match:
        return ""
    raw_id = clean_text(match.group(1))
    if not re.search(r"\\d", raw_id):
        return ""
    safe_id = re.sub(r"[^0-9A-Za-z-]", "-", raw_id)
    return f"KYOTO-{safe_id}"


def _extract_name_detail_maker(cell: BeautifulSoup) -> tuple[str, str, str]:
    name = ""
    detail_url = ""
    for anchor in cell.find_all("a", href=True):
        text = clean_text(anchor.get_text(" ", strip=True))
        if text:
            name = text
            detail_url = urljoin(LIST_URL, anchor["href"])
            break
    if not name:
        name = clean_text(cell.get_text(" ", strip=True))

    maker = ""
    for paragraph in cell.find_all("p"):
        text = clean_text(paragraph.get_text(" ", strip=True))
        if text.startswith("（") and text.endswith("）"):
            maker = text.strip("（）")
            break
    return name, detail_url, maker


def _extract_meta(cell: BeautifulSoup | None) -> tuple[str, str, str, list[str]]:
    if not cell:
        return "", "", "", []
    text = clean_text(cell.get_text(" ", strip=True))
    fee_note = "料金規程" if "料金規程" in text else ""
    campus = _extract_campus(cell)
    location = _extract_location(cell)
    keywords = _extract_keywords(text)
    return location, campus, fee_note, keywords


def _extract_campus(cell: BeautifulSoup) -> str:
    for img in cell.find_all("img"):
        title = img.get("title", "")
        match = re.search(r"([^\s]+?(キャンパス|地区))", title or "")
        if match:
            return clean_text(match.group(1))
    return ""


def _extract_location(cell: BeautifulSoup) -> str:
    for anchor in cell.find_all("a"):
        text = clean_text(anchor.get_text(" ", strip=True))
        if text and text not in LOCATION_SKIP and "料金" not in text:
            return text
    return ""


def _extract_keywords(text: str) -> list[str]:
    keywords: list[str] = []
    for chunk in re.findall(r"#([^#]+)", text):
        for part in re.split(r"[、,]", chunk):
            cleaned = clean_text(part)
            if cleaned:
                keywords.append(cleaned)
    return keywords


def _build_address(campus: str, location: str) -> str:
    parts = [part for part in (campus, location) if part]
    if parts:
        return f"京都大学 {' '.join(parts)}"
    return "京都大学"


def _build_conditions_note(maker: str, keywords: list[str]) -> str:
    parts: list[str] = []
    if maker:
        parts.append(f"メーカー: {maker}")
    if keywords:
        parts.append(f"キーワード: {', '.join(keywords)}")
    return " / ".join(parts)
