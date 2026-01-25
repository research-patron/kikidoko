from __future__ import annotations

import hashlib
import re

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.kochi-u.ac.jp/kms/ct_mrc/facility/Instruments/"
ORG_NAME = "高知大学 総合研究センター 生命機能解析部門 実験実習機器施設・RI実験施設"
PREFECTURE = "高知県"


def fetch_kochi_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    records: list[RawEquipment] = []
    seen: set[str] = set()
    for heading in soup.find_all("h2"):
        category = clean_text(heading.get_text(" ", strip=True))
        if "重要" in category:
            continue
        items = _collect_items(heading)
        if not items:
            continue

        for name in items:
            equipment_id = _build_equipment_id(category, name)
            if equipment_id in seen:
                continue
            seen.add(equipment_id)
            records.append(
                RawEquipment(
                    equipment_id=equipment_id,
                    name=name,
                    category_general=category,
                    org_name=ORG_NAME,
                    prefecture=PREFECTURE,
                    address_raw="高知大学",
                    source_url=LIST_URL,
                )
            )
            if limit and len(records) >= limit:
                return records

    return records


def _collect_items(heading: BeautifulSoup) -> list[str]:
    items: list[str] = []
    node = heading.find_next_sibling()
    while node and node.name not in ("h2", "h3"):
        if node.name in ("ul", "ol"):
            for li in node.find_all("li"):
                text = clean_text(li.get_text(" ", strip=True))
                if text:
                    items.append(text)
        node = node.find_next_sibling()
    return items


def _build_equipment_id(category: str, name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", clean_text(name)).strip("-")
    category_slug = re.sub(r"[^A-Za-z0-9]+", "-", clean_text(category)).strip("-")
    if slug and category_slug:
        return f"KOCHI-{category_slug}-{slug}"
    if slug:
        return f"KOCHI-{slug}"
    digest = hashlib.sha1(f"{category}:{name}".encode("utf-8")).hexdigest()[:10]
    return f"KOCHI-{digest}"
