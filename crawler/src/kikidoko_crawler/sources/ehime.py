from __future__ import annotations

from typing import Iterable

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

BASE_URL = "https://www.adres.ehime-u.ac.jp"
PAGE_PATHS = (
    "/bumon/01/kiki.html",
    "/bumon/02/kiki.html",
    "/bumon/05/kiki.html",
    "/bumon/06/kiki.html",
)
PREFECTURE = "愛媛県"


def fetch_ehime_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    records: list[RawEquipment] = []
    for path in PAGE_PATHS:
        url = f"{BASE_URL}{path}"
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, "html.parser")

        org_name = _extract_org_name(soup)
        for ul in _collect_equipment_lists(soup):
            category_general = _find_heading(ul)
            for li in ul.find_all("li"):
                name, description = _extract_item_text(li)
                if not name:
                    continue
                records.append(
                    RawEquipment(
                        name=name,
                        category_general=category_general,
                        org_name=org_name,
                        prefecture=PREFECTURE,
                        conditions_note=description,
                        source_url=url,
                    )
                )
                if limit and len(records) >= limit:
                    return records

    return records


def _collect_equipment_lists(soup: BeautifulSoup) -> Iterable[BeautifulSoup]:
    for ul in soup.find_all("ul"):
        classes = " ".join(ul.get("class", []))
        if "kiki_list" in classes:
            yield ul


def _extract_org_name(soup: BeautifulSoup) -> str:
    title = clean_text(soup.title.get_text(" ", strip=True)) if soup.title else ""
    parts = [part.strip() for part in title.split("|") if part.strip()]
    division = parts[1] if len(parts) >= 3 else ""
    if division:
        return f"愛媛大学 学術支援センター {division}"
    return "愛媛大学 学術支援センター"


def _find_heading(node: BeautifulSoup) -> str:
    heading = node.find_previous(["h2", "h3"])
    return clean_text(heading.get_text(" ", strip=True)) if heading else ""


def _extract_item_text(item: BeautifulSoup) -> tuple[str, str]:
    title_node = item.find("p", class_="kiki_ttl")
    desc_node = item.find("p", class_="kiki_desc")
    if title_node:
        name = clean_text(title_node.get_text(" ", strip=True))
        description = clean_text(desc_node.get_text(" ", strip=True)) if desc_node else ""
        return name, description
    name = clean_text(item.get_text(" ", strip=True))
    return name, ""
