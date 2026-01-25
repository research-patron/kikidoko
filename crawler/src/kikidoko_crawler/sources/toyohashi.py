from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

ANALYSIS_URL = "https://crfc.tut.ac.jp/analysis/index.html"
ENGINEERING_URL = "https://crfc.tut.ac.jp/engineering/index.html"
ORG_NAME = "豊橋技術科学大学 教育研究基盤センター"
PREFECTURE = "愛知県"

SOURCES = (
    (ANALYSIS_URL, "分析支援部門"),
    (ENGINEERING_URL, "工作支援部門"),
)


def fetch_toyohashi_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    session = requests.Session()
    records: list[RawEquipment] = []
    seen: set[str] = set()

    for list_url, category_general in SOURCES:
        for name, detail_url in _collect_equipment_links(session, list_url, timeout):
            record = _fetch_detail(
                session, detail_url, name, category_general, timeout
            )
            if not record:
                continue
            key = f"{record.name}:{record.source_url}"
            if key in seen:
                continue
            seen.add(key)
            records.append(record)
            if limit and len(records) >= limit:
                return records

    return records


def _collect_equipment_links(
    session: requests.Session, list_url: str, timeout: int
) -> list[tuple[str, str]]:
    response = session.get(list_url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")

    links: list[tuple[str, str]] = []
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "")
        text = clean_text(anchor.get_text(" ", strip=True))
        if not text or href.startswith("../"):
            continue
        if href in {"index.html", "analysis2.html", "engineering2.html"}:
            continue
        if href.endswith(".html"):
            full_url = urljoin(list_url, href)
            if "index_english.html" in full_url:
                continue
            links.append((text, full_url))

    return links


def _fetch_detail(
    session: requests.Session,
    url: str,
    name: str,
    category_general: str,
    timeout: int,
) -> RawEquipment | None:
    if not name:
        return None

    location = _extract_location(session, url, timeout)
    equipment_id = _format_equipment_id(_extract_slug(url))

    return RawEquipment(
        equipment_id=equipment_id,
        name=name,
        category_general=category_general,
        org_name=ORG_NAME,
        prefecture=PREFECTURE,
        address_raw=location,
        source_url=url,
    )


def _extract_location(
    session: requests.Session, url: str, timeout: int
) -> str:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")

    for item in soup.find_all("li"):
        if "設置場所" not in item.get_text(" ", strip=True):
            continue
        table = item.find_next("table")
        if not table:
            return ""
        lines: list[str] = []
        for row in table.find_all("tr"):
            cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
            cells = [cell for cell in cells if cell]
            if cells:
                lines.append(" ".join(cells))
        return " / ".join(lines)

    return ""


def _extract_slug(url: str) -> str:
    path = urlparse(url).path
    name = path.rsplit("/", 1)[-1]
    return re.sub(r"\.html?$", "", name)


def _format_equipment_id(slug: str) -> str:
    if not slug:
        return ""
    safe_slug = "".join(char if char.isalnum() else "-" for char in slug.upper())
    return f"TOYOHASHI-{safe_slug}"
