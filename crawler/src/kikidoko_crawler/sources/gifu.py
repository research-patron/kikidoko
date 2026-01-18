from __future__ import annotations

from urllib.parse import urldefrag, urljoin

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www1.gifu-u.ac.jp/~lsrc/dia/10_instrument.php"
ORG_NAME = "岐阜大学 高等研究院 科学研究基盤センター 機器分析分野"
PREFECTURE = "岐阜県"


def fetch_gifu_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    list_soup = _fetch_soup(LIST_URL, timeout)
    detail_urls = _collect_detail_urls(list_soup)

    records: list[RawEquipment] = []
    for detail_url in detail_urls:
        detail_soup = _fetch_soup(detail_url, timeout)
        for name, category_general in _extract_items(detail_soup):
            records.append(
                RawEquipment(
                    name=name,
                    category_general=category_general,
                    org_name=ORG_NAME,
                    prefecture=PREFECTURE,
                    source_url=detail_url,
                )
            )
            if limit and len(records) >= limit:
                return records

    extra_names = _extract_extra_list_items(list_soup, {record.name for record in records})
    for name in extra_names:
        records.append(
            RawEquipment(
                name=name,
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                source_url=LIST_URL,
            )
        )
        if limit and len(records) >= limit:
            return records

    return records


def _fetch_soup(url: str, timeout: int) -> BeautifulSoup:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    return BeautifulSoup(response.text, "html.parser")


def _collect_detail_urls(soup: BeautifulSoup) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for anchor in soup.select("h4 a[href]"):
        href = anchor["href"]
        if "10_instrument/" not in href:
            continue
        url = urljoin(LIST_URL, href)
        url, _ = urldefrag(url)
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def _extract_items(soup: BeautifulSoup) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    current_category = ""
    for node in soup.find_all(["h3", "h4"]):
        if node.name == "h3":
            category = clean_text(node.get_text(" ", strip=True))
            if category and category != "機器分析分野":
                current_category = category
            continue
        name = clean_text(node.get_text(" ", strip=True))
        if not name or name.casefold() == "link":
            continue
        items.append((name, current_category))
    return items


def _extract_extra_list_items(soup: BeautifulSoup, existing: set[str]) -> list[str]:
    extras: list[str] = []
    for heading in soup.find_all("h4"):
        anchors = heading.find_all("a", href=True)
        if not anchors:
            continue
        text = clean_text(heading.get_text(" ", strip=True))
        if "、" not in text:
            continue
        anchor_names = {clean_text(anchor.get_text(" ", strip=True)) for anchor in anchors}
        for chunk in text.split("、"):
            name = clean_text(chunk)
            for token in ("など", "等"):
                if name.endswith(token):
                    name = clean_text(name[: -len(token)])
            if not name or name in anchor_names or name in existing:
                continue
            extras.append(name)
    return extras
