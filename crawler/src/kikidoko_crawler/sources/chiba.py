from __future__ import annotations

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.cac.chiba-u.ac.jp/equipment/index.html"
ORG_NAME = "千葉大学 共用機器センター"
PREFECTURE = "千葉県"


def fetch_chiba_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")

    records: list[RawEquipment] = []
    for item in soup.find_all("h3"):
        name = _extract_name(item)
        if not name:
            continue
        category_general = _find_category(item)
        location = _extract_location(item)
        description = _extract_description(item)
        source_url = _extract_source_url(item)

        records.append(
            RawEquipment(
                name=name,
                category_general=category_general,
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw=_build_address(location),
                conditions_note=description,
                source_url=source_url,
            )
        )
        if limit and len(records) >= limit:
            return records

    return records


def _find_category(item: BeautifulSoup) -> str:
    heading = item.find_previous("h2")
    return clean_text(heading.get_text(" ", strip=True)) if heading else ""


def _extract_name(item: BeautifulSoup) -> str:
    for child in item.children:
        text = clean_text(str(child)) if child.name is None else ""
        if text:
            return text
    return ""


def _extract_location(item: BeautifulSoup) -> str:
    location = item.find("dl", class_="location")
    if not location:
        return ""
    parts: list[str] = []
    for tag in ["dd", "dt"]:
        value = clean_text(location.find(tag).get_text(" ", strip=True)) if location.find(tag) else ""
        if value:
            parts.append(value)
    return " ".join(parts)


def _extract_description(item: BeautifulSoup) -> str:
    notes: list[str] = []
    for sibling in item.find_next_siblings():
        if sibling.name in ("h2", "h3"):
            break
        if sibling.name == "p":
            text = clean_text(sibling.get_text(" ", strip=True))
            if text:
                notes.append(text)
    return " / ".join(notes)


def _extract_source_url(item: BeautifulSoup) -> str:
    anchor = item.find("a", href=True)
    if anchor:
        return urljoin(LIST_URL, anchor["href"])
    return LIST_URL


def _build_address(location: str) -> str:
    if not location:
        return "千葉大学"
    return f"千葉大学 {location}"
