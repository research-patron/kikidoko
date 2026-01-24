from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.iac.saga-u.ac.jp/database.html"
ORG_NAME = "佐賀大学 総合分析実験センター"
PREFECTURE = "佐賀県"
CATEGORY_GENERAL = "研究設備"


def fetch_saga_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.find("table")
    if not table:
        return []

    records: list[RawEquipment] = []
    seen: set[str] = set()
    for row in table.select("tbody tr"):
        cells = row.find_all("td")
        if len(cells) < 7:
            continue

        level = clean_text(cells[0].get_text(" ", strip=True))
        name = clean_text(cells[1].get_text(" ", strip=True))
        if not name:
            continue
        manufacturer = clean_text(cells[2].get_text(" ", strip=True))
        model = clean_text(cells[3].get_text(" ", strip=True))
        detail_link = cells[4].find("a")
        href = detail_link.get("href") if detail_link else ""
        source_url = urljoin(LIST_URL, href) if href else LIST_URL
        location = clean_text(cells[5].get_text(" ", strip=True))
        contact = clean_text(cells[6].get_text(" ", strip=True))
        external_use = "可" if "全学" in level or "学外" in level else "要相談"

        equipment_id = _build_equipment_id(source_url, name)
        if equipment_id and equipment_id in seen:
            continue
        if equipment_id:
            seen.add(equipment_id)

        records.append(
            RawEquipment(
                equipment_id=equipment_id,
                name=name,
                category_general=CATEGORY_GENERAL,
                category_detail=level,
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw=location,
                external_use=external_use,
                conditions_note=_build_conditions_note(
                    manufacturer, model, contact, source_url
                ),
                source_url=source_url,
            )
        )
        if limit and len(records) >= limit:
            return records

    return records


def _build_conditions_note(
    manufacturer: str, model: str, contact: str, detail_url: str
) -> str:
    parts: list[str] = []
    if manufacturer:
        parts.append(f"メーカー: {manufacturer}")
    if model:
        parts.append(f"型式: {model}")
    if contact:
        parts.append(f"管理担当: {contact}")
    if detail_url and detail_url != LIST_URL:
        parts.append(f"詳細: {detail_url}")
    return " / ".join(parts)


def _build_equipment_id(detail_url: str, name: str) -> str:
    parsed = urlparse(detail_url)
    slug = parsed.path.rstrip("/").split("/")[-1]
    slug = slug.replace(".php", "")
    if slug:
        return f"SAGA-{slug}"
    fallback = re.sub(r"[^A-Za-z0-9]+", "-", clean_text(name)).strip("-")
    return f"SAGA-{fallback}" if fallback else ""
