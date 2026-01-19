from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://kiki.web.nitech.ac.jp/list/"
ORG_NAME = "名古屋工業大学"
PREFECTURE = "愛知県"
CATEGORY_GENERAL = "分析装置・機器紹介"
BASE_ADDRESS = "名古屋工業大学"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch_nitech_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    session = requests.Session()
    session.headers.update(HEADERS)
    soup = _fetch_page(session, LIST_URL, timeout)
    if not soup:
        return []

    table = soup.find("table")
    if not table:
        return []

    records: list[RawEquipment] = []
    current_room = ""
    for row in table.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if not cells:
            continue
        texts = [clean_text(cell.get_text(" ", strip=True)) for cell in cells]
        if texts and "測定室" in texts[0] and "装置・機器" in " ".join(texts):
            continue

        if cells[0].name == "th":
            current_room = texts[0]
            if len(cells) < 3:
                continue
            equipment_cell = cells[1]
            location_cell = cells[2]
        else:
            if len(cells) < 2:
                continue
            equipment_cell = cells[0]
            location_cell = cells[1]

        name, maker, model, detail_url = _parse_equipment_cell(equipment_cell)
        if not name:
            continue
        address_raw, external_use = _parse_location(location_cell)
        equipment_id = _build_equipment_id(detail_url, name)
        conditions_note = _build_conditions_note(maker, model)

        records.append(
            RawEquipment(
                equipment_id=equipment_id,
                name=name,
                category_general=CATEGORY_GENERAL,
                category_detail=current_room,
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw=address_raw,
                external_use=external_use,
                conditions_note=conditions_note,
                source_url=detail_url or LIST_URL,
            )
        )

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


def _parse_equipment_cell(cell: Tag) -> tuple[str, str, str, str]:
    anchor = cell.find("a", href=True)
    name = clean_text(anchor.get_text(" ", strip=True)) if anchor else ""
    detail_url = urljoin(LIST_URL, anchor["href"]) if anchor else ""
    full_text = clean_text(cell.get_text(" ", strip=True))
    if not name:
        name = full_text

    maker = ""
    model = ""
    if anchor:
        remainder = full_text.replace(name, "", 1).strip()
        maker, model = _split_maker_model(remainder)

    return name, maker, model, detail_url


def _split_maker_model(text: str) -> tuple[str, str]:
    if not text:
        return "", ""
    parts = re.split(r"\\s*[／/]\\s*", text, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", ""


def _parse_location(cell: Tag) -> tuple[str, str]:
    location_text = clean_text(cell.get_text(" ", strip=True))
    if not location_text:
        return BASE_ADDRESS, "要相談"
    parts = [part.strip() for part in location_text.split("・") if part.strip()]
    address = parts[0] if parts else location_text
    scope = "・".join(parts[1:]) if len(parts) > 1 else ""
    external_use = _normalize_scope(scope)
    return _build_address(address), external_use


def _normalize_scope(value: str) -> str:
    if "学内外" in value or "学外" in value:
        return "可"
    if "学内のみ" in value or "学内限定" in value:
        return "不可"
    if value:
        return "要相談"
    return "要相談"


def _build_address(location: str) -> str:
    if not location:
        return BASE_ADDRESS
    if "名古屋" in location or "大学" in location:
        return location
    return f"{BASE_ADDRESS} {location}"


def _build_conditions_note(maker: str, model: str) -> str:
    parts: list[str] = []
    if maker:
        parts.append(f"メーカー: {maker}")
    if model:
        parts.append(f"型番: {model}")
    return " / ".join(parts)


def _build_equipment_id(detail_url: str, name: str) -> str:
    if detail_url:
        parsed = urlparse(detail_url)
        slug = parsed.path.rstrip("/").rsplit("/", 1)[-1]
        if slug:
            return f"NITECH-{slug}"
    return ""
