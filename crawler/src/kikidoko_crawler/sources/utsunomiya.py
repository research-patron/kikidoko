from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.cia.utsunomiya-u.ac.jp/equipment/"
ORG_NAME = "宇都宮大学 研究推進機構 機器分析センター"
PREFECTURE = "栃木県"


def fetch_utsunomiya_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    entry_body = soup.select_one(".entry-body") or soup
    records: list[RawEquipment] = []
    seen: set[str] = set()
    current_section = ""
    current_group = ""

    for child in entry_body.find_all(recursive=False):
        if child.name == "h2":
            current_section = clean_text(child.get_text(" ", strip=True))
            current_group = ""
            continue

        heading = child.find("h3")
        if heading:
            current_group = clean_text(heading.get_text(" ", strip=True))

        for accordion in child.select(".c-accordion__content"):
            for columns in accordion.select("div.wp-block-columns"):
                record = _parse_equipment(columns, current_section, current_group)
                if not record:
                    continue
                if record.name in seen:
                    continue
                seen.add(record.name)
                records.append(record)
                if limit and len(records) >= limit:
                    return records

    return records


def _parse_equipment(
    columns: BeautifulSoup, category_general: str, category_detail: str
) -> RawEquipment | None:
    text_column = None
    for column in columns.select("div.wp-block-column"):
        if column.find("strong"):
            text_column = column
            break
    if not text_column:
        return None

    name_node = text_column.find("strong")
    name = clean_text(name_node.get_text(" ", strip=True)) if name_node else ""
    if not name:
        return None

    paragraphs = [clean_text(p.get_text(" ", strip=True)) for p in text_column.find_all("p")]
    maker_model = ""
    description = ""
    location = ""
    contact = ""

    for text in paragraphs:
        if not text or text == name:
            continue
        if "設置場所" in text or "問い合せ" in text or "問い合わせ" in text:
            location, contact = _split_location_contact(text)
            continue
        if not maker_model:
            maker_model = _strip_name(text, name)
            continue
        if not description:
            description = text
        else:
            description = f"{description} {text}"

    if not maker_model and paragraphs:
        maker_model = _strip_name(paragraphs[0], name)

    conditions_note = _build_conditions_note(maker_model, description, contact)
    address_raw = _build_address(location)

    return RawEquipment(
        name=name,
        category_general=category_general,
        category_detail=category_detail,
        org_name=ORG_NAME,
        prefecture=PREFECTURE,
        address_raw=address_raw,
        conditions_note=conditions_note,
        source_url=LIST_URL,
    )


def _strip_name(text: str, name: str) -> str:
    if not text:
        return ""
    if text.startswith(name):
        return text[len(name) :].strip()
    return text.replace(name, "", 1).strip()


def _split_location_contact(text: str) -> tuple[str, str]:
    location = text
    contact = ""
    parts = re.split(r"お?問合せ|問い合せ|問い合わせ", text, maxsplit=1)
    if len(parts) == 2:
        location, contact = parts[0], parts[1]
    location = re.sub(r"^設置場所[\\s：:]*", "", location).strip()
    contact = re.sub(r"^[\\s：:]*", "", contact).strip()
    return location, contact


def _build_conditions_note(maker_model: str, description: str, contact: str) -> str:
    parts: list[str] = []
    if maker_model:
        parts.append(f"メーカー/型式: {maker_model}")
    if description:
        parts.append(f"概要: {description}")
    if contact:
        parts.append(f"問合せ: {contact}")
    return " / ".join(parts)


def _build_address(location: str) -> str:
    if location:
        return f"宇都宮大学 {location}"
    return ORG_NAME
