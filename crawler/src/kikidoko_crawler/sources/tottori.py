from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

BASE_URL = "https://orip.tottori-u.ac.jp/setsubi/"
API_URL = "https://orip.tottori-u.ac.jp/setsubi/wp-json/wp/v2/machine"
ORG_NAME = "鳥取大学 共同利用設備"
PREFECTURE = "鳥取県"
FALLBACK_CATEGORY = "研究設備"


def fetch_tottori_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    session = requests.Session()
    records: list[RawEquipment] = []
    seen: set[str] = set()

    page = 1
    total_pages = 1
    while page <= total_pages:
        url = f"{API_URL}?per_page=100&page={page}"
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        total_pages = int(response.headers.get("X-WP-TotalPages", "1"))
        items = response.json()

        for item in items:
            title_html = item.get("title", {}).get("rendered", "")
            fallback_name = _clean_html(title_html)
            link = item.get("link") or ""
            record = _fetch_detail(session, link, fallback_name, timeout)
            if not record:
                continue
            key = record.equipment_id or f"{record.name}:{record.source_url}"
            if key in seen:
                continue
            seen.add(key)
            records.append(record)
            if limit and len(records) >= limit:
                return records

        page += 1

    return records


def _fetch_detail(
    session: requests.Session, url: str, fallback_name: str, timeout: int
) -> RawEquipment | None:
    if not url:
        return None
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")

    name = _extract_name(soup) or fallback_name
    if not name:
        return None

    categories = _extract_categories(soup)
    category_general = categories[0] if categories else FALLBACK_CATEGORY
    category_detail = " / ".join(categories[1:]) if len(categories) > 1 else ""

    equipment_id = _extract_equipment_id(soup) or _extract_id_from_slug(url)
    info = _extract_info_map(soup)
    location = info.get("設置場所", "")
    external_use = info.get("利用対象者", "")
    fee_note = _join_fee_notes(info)
    maker = info.get("メーカー", "")
    model = info.get("型番", "")
    conditions_note = _build_conditions_note(maker, model)

    return RawEquipment(
        equipment_id=_format_equipment_id(equipment_id),
        name=name,
        category_general=category_general,
        category_detail=category_detail,
        org_name=ORG_NAME,
        prefecture=PREFECTURE,
        address_raw=location,
        external_use=external_use,
        fee_note=fee_note,
        conditions_note=conditions_note,
        source_url=url,
    )


def _clean_html(value: str) -> str:
    if not value:
        return ""
    return clean_text(BeautifulSoup(value, "html.parser").get_text(" ", strip=True))


def _extract_name(soup: BeautifulSoup) -> str:
    title = soup.select_one(".eqpt_inside h1")
    if title:
        return clean_text(title.get_text(" ", strip=True))
    return ""


def _extract_categories(soup: BeautifulSoup) -> list[str]:
    categories: list[str] = []
    for span in soup.select(".classificationsList .classification"):
        text = clean_text(span.get_text(" ", strip=True))
        if text:
            categories.append(text)
    return categories


def _extract_equipment_id(soup: BeautifulSoup) -> str:
    text = ""
    node = soup.select_one(".eqptID")
    if node:
        text = clean_text(node.get_text(" ", strip=True))
    match = re.search(r"設備ID[:：]\\s*(\\d+)", text)
    return match.group(1) if match else ""


def _extract_id_from_slug(url: str) -> str:
    path = urlparse(url).path
    match = re.search(r"id(\\d+)", path)
    return match.group(1) if match else ""


def _format_equipment_id(raw_id: str) -> str:
    if not raw_id:
        return ""
    return f"TOTTORI-{raw_id}"


def _extract_info_map(soup: BeautifulSoup) -> dict[str, str]:
    info: dict[str, str] = {}
    for item in soup.select("ul.eqpt_info li"):
        label_node = item.select_one(".dt")
        value_node = item.select_one(".dd")
        if not label_node or not value_node:
            continue
        label = clean_text(label_node.get_text(" ", strip=True))
        value = clean_text(value_node.get_text(" ", strip=True))
        if label and value:
            info[label] = value
    return info


def _join_fee_notes(info: dict[str, str]) -> str:
    parts: list[str] = []
    for key, value in info.items():
        if "利用料金" in key:
            if key == "利用料金":
                parts.append(value)
            else:
                parts.append(f"{key}: {value}")
    return " / ".join(parts)


def _build_conditions_note(maker: str, model: str) -> str:
    notes: list[str] = []
    if maker:
        notes.append(f"メーカー: {maker}")
    if model:
        notes.append(f"型番: {model}")
    return " / ".join(notes)
