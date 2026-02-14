from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://arim.yz.yamagata-u.ac.jp/equip.html"
ORG_NAME = "山形大学 ARIM（工学部共同機器分析センター）"
PREFECTURE = "山形県"
CATEGORY_GENERAL = "ARIM共用装置"
CODE_RE = re.compile(r"\(([A-Za-z0-9\-]+)\)")


def fetch_yamagata_u_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    records: list[RawEquipment] = []
    seen_ids: set[str] = set()
    for index, anchor in enumerate(soup.select("article.equipment-box > a[href]"), start=1):
        href = clean_text(anchor.get("href", ""))
        if not href:
            continue
        title = clean_text((anchor.select_one(".txt h4") or anchor).get_text(" ", strip=True))
        if not title:
            continue
        model = clean_text(
            (anchor.select_one(".txt .num") or {}).get_text(" ", strip=True)
            if anchor.select_one(".txt .num")
            else ""
        )
        description = ""
        for paragraph in anchor.select(".txt p"):
            if "num" in (paragraph.get("class") or []):
                continue
            description = clean_text(paragraph.get_text(" ", strip=True))
            if description:
                break

        equipment_id = _build_equipment_id(title, index)
        if equipment_id in seen_ids:
            continue
        seen_ids.add(equipment_id)
        source_url = urljoin(LIST_URL, href)

        conditions_parts = []
        if model:
            conditions_parts.append(f"型番: {model}")
        if description:
            conditions_parts.append(f"概要: {description}")
        conditions_note = " / ".join(conditions_parts)

        records.append(
            RawEquipment(
                equipment_id=equipment_id,
                name=title,
                category_general=CATEGORY_GENERAL,
                category_detail=_to_category_detail(title),
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw="山形大学 米沢キャンパス",
                external_use="可",
                fee_note="利用料金は装置ページごとに案内",
                conditions_note=_truncate(conditions_note, 800),
                source_url=source_url,
            )
        )
        if limit and len(records) >= limit:
            return records

    return records


def _build_equipment_id(title: str, index: int) -> str:
    match = CODE_RE.search(title)
    if match:
        return f"YAMAGATA-U-{match.group(1).upper()}"
    return f"YAMAGATA-U-{index:03d}"


def _to_category_detail(title: str) -> str:
    value = clean_text(title)
    if "(" in value:
        value = clean_text(value.split("(", 1)[0])
    return value


def _truncate(value: str, max_len: int) -> str:
    value = clean_text(value)
    if len(value) <= max_len:
        return value
    return f"{value[: max_len - 1]}…"
