from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

INDEX_URL = "https://web.tuat.ac.jp/~kiki/index.html"
ORG_NAME = "東京農工大学 学術研究支援総合センター 機器分析施設"
PREFECTURE = "東京都"
CATEGORY_GENERAL = "機器分析施設"


def fetch_tuat_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(INDEX_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")

    records: list[RawEquipment] = []
    for url in _collect_instrument_links(soup):
        record = _fetch_instrument(url, timeout)
        if not record:
            continue
        records.append(record)
        if limit and len(records) >= limit:
            return records

    return records


def _collect_instrument_links(soup: BeautifulSoup) -> list[str]:
    urls: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "")
        if "instrument/" not in href:
            continue
        urls.add(urljoin(INDEX_URL, href))
    return sorted(urls)


def _fetch_instrument(url: str, timeout: int) -> RawEquipment | None:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")

    sections = _collect_sections(soup)
    name = _section_value(sections, "機器名称") or _fallback_title(soup)
    if not name:
        return None

    location = _section_value(sections, "設置場所")
    contact = _extract_contact(sections)
    fee_note = _extract_fee_note(sections)
    equipment_id = _format_equipment_id(_extract_slug(url))

    return RawEquipment(
        equipment_id=equipment_id,
        name=name,
        category_general=CATEGORY_GENERAL,
        org_name=ORG_NAME,
        prefecture=PREFECTURE,
        address_raw=location or "東京農工大学",
        fee_note=fee_note,
        conditions_note=contact,
        source_url=url,
    )


def _collect_sections(soup: BeautifulSoup) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    for h3 in soup.find_all("h3"):
        title = clean_text(h3.get_text(" ", strip=True))
        lines = _section_lines(h3)
        sections.append((title, lines))
    return sections


def _section_lines(h3: BeautifulSoup) -> list[str]:
    lines: list[str] = []
    for sibling in h3.next_siblings:
        if getattr(sibling, "name", None) == "h3":
            break
        if not hasattr(sibling, "get_text"):
            continue
        text = sibling.get_text("\n", strip=True)
        for line in text.split("\n"):
            cleaned = clean_text(line)
            if cleaned:
                lines.append(cleaned)
    return lines


def _section_value(sections: list[tuple[str, list[str]]], title: str) -> str:
    for section_title, lines in sections:
        if title in section_title and lines:
            return " ".join(lines)
    return ""


def _extract_contact(sections: list[tuple[str, list[str]]]) -> str:
    for title, lines in sections:
        if not lines:
            continue
        if "問い合わせ" in title or "連絡" in title:
            return " / ".join(lines)
    for title, lines in sections:
        if title:
            continue
        text = " ".join(lines)
        if any(keyword in text for keyword in ("MAIL", "内線", "電話", "連絡")):
            return " / ".join(lines)
    return ""


def _extract_fee_note(sections: list[tuple[str, list[str]]]) -> str:
    fee_lines: list[str] = []
    for title, lines in sections:
        if "料金" in title:
            fee_lines.extend(lines)
    if not fee_lines:
        for title, lines in sections:
            if "利用方法" in title:
                fee_lines = [
                    line
                    for line in lines
                    if ("料金" in line or "円" in line or "有料" in line)
                ]
                break
    cleaned = [line for line in fee_lines if not _is_fee_heading(line)]
    return " / ".join(_dedupe_lines(cleaned)[:5])


def _dedupe_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        unique.append(line)
    return unique


def _is_fee_heading(line: str) -> bool:
    if line == "利用料金":
        return True
    return re.fullmatch(r"\d+\.?\s*利用料金", line) is not None


def _extract_slug(url: str) -> str:
    path = urlparse(url).path
    name = path.rsplit("/", 1)[-1]
    return re.sub(r"\.html?$", "", name)


def _format_equipment_id(slug: str) -> str:
    if not slug:
        return ""
    safe_slug = "".join(char if char.isalnum() else "-" for char in slug.upper())
    return f"TUAT-{safe_slug}"


def _fallback_title(soup: BeautifulSoup) -> str:
    if not soup.title:
        return ""
    title = clean_text(soup.title.get_text(" ", strip=True))
    return title.split("｜", 1)[0].strip()
