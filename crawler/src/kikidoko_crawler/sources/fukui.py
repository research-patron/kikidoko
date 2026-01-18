from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://dinosaur.fir.u-fukui.ac.jp/research/equipment/"
ORG_NAME = "福井大学 遠赤外領域開発研究センター"
PREFECTURE = "福井県"
CATEGORY_GENERAL = "基盤装置"


def fetch_fukui_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")
    container = soup.find("article") or soup

    records: list[RawEquipment] = []
    for heading in _iter_equipment_headings(container):
        name = _extract_name(heading)
        if not name:
            continue
        description = _extract_description(heading)
        records.append(
            RawEquipment(
                name=name,
                category_general=CATEGORY_GENERAL,
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw=ORG_NAME,
                conditions_note=description,
                source_url=LIST_URL,
            )
        )
        if limit and len(records) >= limit:
            return records

    return records


def _iter_equipment_headings(container: BeautifulSoup) -> list[BeautifulSoup]:
    headings: list[BeautifulSoup] = []
    for node in container.find_all(["h2", "h3"]):
        text = clean_text(node.get_text(" ", strip=True))
        if node.name == "h2" and "共同研究" in text:
            break
        if node.name == "h3" and text:
            headings.append(node)
    return headings


def _extract_name(heading: BeautifulSoup) -> str:
    text = clean_text(heading.get_text(" ", strip=True))
    return re.sub(r"^\d+\.\s*", "", text)


def _extract_description(heading: BeautifulSoup) -> str:
    notes: list[str] = []
    for sibling in heading.find_next_siblings():
        if sibling.name in ("h2", "h3"):
            break
        if sibling.name in ("p", "ul", "ol", "div"):
            text = clean_text(sibling.get_text(" ", strip=True))
            if text:
                notes.append(text)
    return " / ".join(notes)
