from __future__ import annotations

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.cia.kagoshima-u.ac.jp/home/list.html"
ORG_NAME = "鹿児島大学 先端科学研究推進センター 機器分析部門"
PREFECTURE = "鹿児島県"
CATEGORY_GENERAL = "機器分析部門"
SKIP_TEXTS = {
    "機器分析部門 機器リスト",
    "ページの先頭へ戻る",
}


def fetch_kagoshima_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = "cp932"
    soup = BeautifulSoup(response.text, "html.parser")

    body = soup.find("body") or soup
    records: list[RawEquipment] = []
    seen: set[tuple[str, str]] = set()
    name_seen: set[str] = set()
    current_section = ""

    for node in body.descendants:
        if isinstance(node, Tag) and node.name == "a":
            text = clean_text(node.get_text(" ", strip=True))
            if _is_section(text):
                current_section = text
                continue
            if not text or _should_skip(text):
                continue
            display_name = _maybe_disambiguate(text, current_section, name_seen)
            record = _build_record(display_name, current_section, node.get("href"))
            if _is_duplicate(record, seen):
                continue
            records.append(record)
        elif isinstance(node, NavigableString):
            if node.parent and getattr(node.parent, "name", "") == "a":
                continue
            text = clean_text(str(node))
            if _is_section(text):
                current_section = text
                continue
            if not text or _should_skip(text):
                continue
            display_name = _maybe_disambiguate(text, current_section, name_seen)
            record = _build_record(display_name, current_section, "")
            if _is_duplicate(record, seen):
                continue
            records.append(record)

        if limit and len(records) >= limit:
            return records

    return records


def _is_section(text: str) -> bool:
    return text.startswith("【") and text.endswith("】")


def _should_skip(text: str) -> bool:
    if text in SKIP_TEXTS:
        return True
    if text in {"[", "]"}:
        return True
    return False


def _build_record(name: str, section: str, href: str) -> RawEquipment:
    detail = _strip_brackets(section)
    return RawEquipment(
        name=name,
        category_general=CATEGORY_GENERAL,
        category_detail=detail,
        org_name=ORG_NAME,
        prefecture=PREFECTURE,
        address_raw=_build_address(detail),
        source_url=_build_source_url(href),
    )


def _build_source_url(href: str) -> str:
    if not href:
        return LIST_URL
    return urljoin(LIST_URL, href)


def _strip_brackets(section: str) -> str:
    text = section.strip()
    if text.startswith("【") and text.endswith("】"):
        return text[1:-1]
    return text


def _build_address(section: str) -> str:
    if section:
        return f"鹿児島大学 {section}"
    return "鹿児島大学"


def _maybe_disambiguate(name: str, section: str, seen: set[str]) -> str:
    if name in seen:
        detail = _strip_brackets(section)
        if detail:
            return f"{name} ({detail})"
    seen.add(name)
    return name


def _is_duplicate(record: RawEquipment, seen: set[tuple[str, str]]) -> bool:
    key = (record.name, record.category_detail)
    if key in seen:
        return True
    seen.add(key)
    return False
