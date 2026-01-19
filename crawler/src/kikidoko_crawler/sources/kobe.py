from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

BASE_URL = "http://www.csrea.kobe-u.ac.jp/"
LIST_URL = urljoin(BASE_URL, "roomshiryo_kiki.html")
ORG_NAME = "神戸大学 研究基盤センター 機器分析部門"
PREFECTURE = "兵庫県"
CATEGORY_GENERAL = "機器分析部門"


def fetch_kobe_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    records: list[RawEquipment] = []
    seen: set[str] = set()

    for record in _fetch_sample_room_records(timeout):
        if record.name in seen:
            continue
        seen.add(record.name)
        records.append(record)
        if limit and len(records) >= limit:
            return records

    for url in _fetch_detail_urls(timeout):
        record = _fetch_detail_record(url, timeout)
        if not record or record.name in seen:
            continue
        seen.add(record.name)
        records.append(record)
        if limit and len(records) >= limit:
            return records

    return records


def _fetch_sample_room_records(timeout: int) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")

    location = _extract_sample_room_location(soup)
    address_raw = _build_address(location)
    equipment_list = _extract_sample_room_items(soup)

    records: list[RawEquipment] = []
    for name in equipment_list:
        records.append(
            RawEquipment(
                name=name,
                category_general=CATEGORY_GENERAL,
                category_detail="試料作製室",
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw=address_raw,
                source_url=LIST_URL,
            )
        )
    return records


def _fetch_detail_urls(timeout: int) -> list[str]:
    response = requests.get(BASE_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")
    urls: set[str] = set()
    for anchor in soup.select('a[href*="syousai_"]'):
        href = anchor.get("href", "")
        if not href:
            continue
        urls.add(urljoin(BASE_URL, href))
    return sorted(urls)


def _fetch_detail_record(url: str, timeout: int) -> RawEquipment | None:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")
    name = _extract_heading(soup)
    if not name:
        return None
    details = _extract_table_details(soup)
    conditions_note = _build_detail_note(details, soup, name)

    return RawEquipment(
        name=name,
        category_general=CATEGORY_GENERAL,
        org_name=ORG_NAME,
        prefecture=PREFECTURE,
        address_raw="神戸大学 研究基盤センター",
        conditions_note=conditions_note,
        source_url=url,
    )


def _extract_sample_room_location(soup: BeautifulSoup) -> str:
    for text in soup.stripped_strings:
        if "試料作製室" in text:
            match = re.search(r"試料作製室[（(](.*?)[）)]", text)
            if match:
                return clean_text(match.group(1))
    return ""


def _extract_sample_room_items(soup: BeautifulSoup) -> list[str]:
    for strong in soup.find_all("strong"):
        if "設置備品" in clean_text(strong.get_text(" ", strip=True)):
            ul = strong.find_parent().find_next("ul")
            if not ul:
                break
            names = [clean_text(li.get_text(" ", strip=True)) for li in ul.find_all("li")]
            return [name for name in names if name]
    return []


def _extract_heading(soup: BeautifulSoup) -> str:
    for tag in ("h1", "h2", "h3"):
        heading = soup.find(tag)
        if heading:
            text = clean_text(heading.get_text(" ", strip=True))
            if text:
                return text
    return ""


def _extract_table_details(soup: BeautifulSoup) -> dict[str, str]:
    for table in soup.find_all("table"):
        details: dict[str, str] = {}
        for row in table.find_all("tr"):
            cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
            if len(cells) < 2:
                continue
            key = cells[0]
            value = cells[1]
            if key:
                details[key] = value
        if details:
            return details
    return {}


def _build_detail_note(details: dict[str, str], soup: BeautifulSoup, name: str) -> str:
    if details:
        parts = [f"{key}: {value}" for key, value in details.items() if value]
        return " / ".join(parts)

    for paragraph in soup.find_all("p"):
        text = clean_text(paragraph.get_text(" ", strip=True))
        if text and text != name:
            return text
    return ""


def _build_address(location: str) -> str:
    if location:
        return f"神戸大学 {location}"
    return "神戸大学"
