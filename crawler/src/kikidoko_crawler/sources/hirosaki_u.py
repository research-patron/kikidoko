from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.innovation.hirosaki-u.ac.jp/kiki/list.html"
ORG_NAME = "弘前大学 共用機器基盤センター"
PREFECTURE = "青森県"
CATEGORY_GENERAL = "共用機器"
SECTION_ID_RE = re.compile(r"kiki-(\d+)")


def fetch_hirosaki_u_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    records: list[RawEquipment] = []
    seen_ids: set[str] = set()
    for section in soup.select("section.kiki-sec"):
        section_id = clean_text(section.get("id", ""))
        equipment_id = _build_equipment_id(section_id)
        if equipment_id in seen_ids:
            continue

        name_node = section.select_one("h2.kiki-title")
        name = clean_text(name_node.get_text(" ", strip=True)) if name_node else ""
        if not name:
            continue

        field_map = _extract_field_map(section)
        booking_url = _extract_first_booking_url(section)
        source_url = f"{LIST_URL}#{section_id}" if section_id else LIST_URL
        if booking_url:
            source_url = booking_url

        location = field_map.get("機器設置部局", ORG_NAME)
        conditions_note = _build_conditions_note(field_map)
        fee_note = field_map.get("利用料金", "")

        records.append(
            RawEquipment(
                equipment_id=equipment_id,
                name=name,
                category_general=CATEGORY_GENERAL,
                category_detail=field_map.get("使用目的", ""),
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw=location,
                external_use="可",
                fee_note=_truncate(fee_note, 280),
                conditions_note=_truncate(conditions_note, 1200),
                source_url=source_url,
            )
        )
        seen_ids.add(equipment_id)
        if limit and len(records) >= limit:
            return records

    return records


def _extract_field_map(section: BeautifulSoup) -> dict[str, str]:
    field_map: dict[str, str] = {}
    for h4 in section.select("h4"):
        key = clean_text(h4.get_text(" ", strip=True))
        if not key:
            continue
        values: list[str] = []
        node = h4.find_next_sibling()
        while node and getattr(node, "name", "") != "h4":
            text = clean_text(node.get_text(" ", strip=True))
            if text:
                values.append(text)
            node = node.find_next_sibling()
        if values:
            field_map[key] = " / ".join(values)
    return field_map


def _extract_first_booking_url(section: BeautifulSoup) -> str:
    for anchor in section.select("a[href]"):
        href = clean_text(anchor.get("href", ""))
        if not href:
            continue
        if "booking" in href or "records" in href:
            return urljoin(LIST_URL, href)
    return ""


def _build_equipment_id(section_id: str) -> str:
    match = SECTION_ID_RE.search(section_id)
    if match:
        return f"HIROSAKI-{match.group(1)}"
    fallback = re.sub(r"[^A-Za-z0-9]+", "-", section_id).strip("-")
    if fallback:
        return f"HIROSAKI-{fallback.upper()}"
    return "HIROSAKI-UNKNOWN"


def _build_conditions_note(field_map: dict[str, str]) -> str:
    label_order = [
        "型番",
        "メーカー名",
        "導入年度",
        "構成",
        "使用目的",
        "概要・性能",
        "利用の注意事項",
    ]
    parts: list[str] = []
    for label in label_order:
        value = clean_text(field_map.get(label, ""))
        if value:
            parts.append(f"{label}: {value}")
    return " / ".join(parts)


def _truncate(value: str, max_len: int) -> str:
    value = clean_text(value)
    if len(value) <= max_len:
        return value
    return f"{value[: max_len - 1]}…"

