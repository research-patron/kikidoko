from __future__ import annotations

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://facility-mgmt.hiroshima-u.ac.jp/equipment.html"
ORG_NAME = "広島大学 自然科学研究支援開発センター 機器共用・分析部門"
PREFECTURE = "広島県"


def fetch_hiroshima_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")
    content = soup.find(id="main") or soup

    records: list[RawEquipment] = []
    current_category = ""
    for node in content.find_all(["h4", "table"]):
        if node.name == "h4":
            current_category = clean_text(node.get_text(" ", strip=True))
            continue
        if "設置場所" not in node.get_text(" ", strip=True):
            continue
        name, location = _extract_name_location(node)
        if not name:
            continue
        source_url = _extract_source_url(node)
        external_use, usage_note = _extract_usage(node)

        records.append(
            RawEquipment(
                name=name,
                category_general=current_category,
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw=_build_address(location),
                external_use=external_use,
                conditions_note=usage_note,
                source_url=source_url,
            )
        )
        if limit and len(records) >= limit:
            return records

    return records


def _extract_name_location(table: BeautifulSoup) -> tuple[str, str]:
    rows = table.find_all("tr")
    if not rows:
        return "", ""
    title = clean_text(rows[0].get_text(" ", strip=True))

    model = ""
    location = ""
    if len(rows) > 1:
        cells = rows[1].find_all(["th", "td"])
        if cells:
            model = clean_text(cells[0].get_text(" ", strip=True))
        for cell in cells[1:]:
            text = clean_text(cell.get_text(" ", strip=True))
            if "設置場所" in text:
                location = clean_text(text.replace("設置場所：", "").replace("設置場所:", ""))
                break

    if title and model and model not in title:
        name = f"{title} ({model})"
    else:
        name = title or model
    return name, location


def _extract_source_url(table: BeautifulSoup) -> str:
    for anchor in table.find_all("a", href=True):
        href = anchor["href"]
        if href.startswith("javascript"):
            continue
        if "facility-mgmt.hiroshima-u.ac.jp" in href:
            return urljoin(LIST_URL, href)
        if href.startswith("/equipment/") or href.startswith("equipment/"):
            return urljoin(LIST_URL, href)
    return LIST_URL


def _extract_usage(table: BeautifulSoup) -> tuple[str, str]:
    rows = table.find_all("tr")
    if len(rows) < 3:
        return "", ""
    cells = [
        clean_text(cell.get_text(" ", strip=True))
        for cell in rows[2].find_all(["th", "td"])
    ]
    cells = [cell for cell in cells if cell]
    if not cells:
        return "", ""
    usage_text = " / ".join(cells)
    external_use = "可" if "学外" in usage_text else ""
    return external_use, f"利用区分: {usage_text}"


def _build_address(location: str) -> str:
    if location:
        return f"広島大学 {location}"
    return "広島大学"
