from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.hama-med.ac.jp/research/equipment.html"
ORG_NAME = "浜松医科大学 光医学総合研究所 先進機器共用推進部"
PREFECTURE = "静岡県"
CATEGORY_GENERAL = "研究設備"


def fetch_hamamatsu_med_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    records: list[RawEquipment] = []
    seen_names: set[str] = set()
    section_notes = _build_section_notes(soup)
    for section, block in section_notes.items():
        for name in _extract_equipment_names(block):
            normalized_name = clean_text(name)
            if not normalized_name or normalized_name in seen_names:
                continue
            seen_names.add(normalized_name)
            records.append(
                RawEquipment(
                    equipment_id=f"HAMAMED-{len(records) + 1:03d}",
                    name=normalized_name,
                    category_general=CATEGORY_GENERAL,
                    category_detail=section,
                    org_name=ORG_NAME,
                    prefecture=PREFECTURE,
                    address_raw=ORG_NAME,
                    external_use="可",
                    fee_note="利用料金は機器ごとに設定（外部利用可）",
                    conditions_note=_truncate(block, 1200),
                    source_url=LIST_URL,
                )
            )
            if limit and len(records) >= limit:
                return records
    return records


def _build_section_notes(soup: BeautifulSoup) -> dict[str, str]:
    section_notes: dict[str, str] = {}
    for heading in soup.select("h3"):
        section = clean_text(heading.get_text(" ", strip=True))
        if not section:
            continue
        lines: list[str] = []
        node = heading.find_next_sibling()
        while node and getattr(node, "name", "") != "h3":
            node_name = getattr(node, "name", "")
            if node_name == "ul":
                for li in node.find_all("li", recursive=False):
                    text = clean_text(li.get_text(" ", strip=True))
                    if text:
                        lines.append(text)
            elif node_name in {"p", "li"}:
                text = clean_text(node.get_text(" ", strip=True))
                if text:
                    lines.append(text)
            node = node.find_next_sibling()
        if lines:
            section_notes[section] = " / ".join(lines)
    return section_notes


def _extract_equipment_names(section_text: str) -> list[str]:
    text = clean_text(section_text)
    names: list[str] = []
    for prefix in ("主な共用機器：", "共用機器："):
        if prefix not in text:
            continue
        value = text.split(prefix, 1)[1]
        value = re.split(r"(外部の利用：|設置場所：|連絡先：)", value, maxsplit=1)[0]
        value = re.sub(r"（\s*研究\s*用\s*）", "", value)
        value = re.sub(r"（\s*臨床\s*用\s*）", "", value)
        for part in _split_outside_parentheses(value):
            item = clean_text(part)
            if not item:
                continue
            item = item.strip("/")
            item = item.removesuffix("等")
            if len(item) < 2:
                continue
            names.append(item)
    return names


def _split_outside_parentheses(value: str) -> list[str]:
    parts: list[str] = []
    buffer: list[str] = []
    depth = 0
    for ch in value:
        if ch in "（(":
            depth += 1
        elif ch in "）)" and depth > 0:
            depth -= 1
        if ch in "、,，" and depth == 0:
            part = "".join(buffer).strip()
            if part:
                parts.append(part)
            buffer = []
            continue
        buffer.append(ch)
    tail = "".join(buffer).strip()
    if tail:
        parts.append(tail)
    return parts


def _truncate(value: str, max_len: int) -> str:
    value = clean_text(value)
    if len(value) <= max_len:
        return value
    return f"{value[: max_len - 1]}…"
