from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.kitcia.kyutech.ac.jp/instrument_all/"
ORG_NAME = "九州工業大学 機器分析センター"
PREFECTURE = "福岡県"


def fetch_kyutech_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    records: list[RawEquipment] = []
    for group in soup.select("div.wp-block-group"):
        name_tag = group.select_one("p.model_name")
        if not name_tag:
            continue
        name = _extract_name(name_tag)
        if not name:
            continue

        table = group.find("table")
        details = _extract_details(table)
        address_raw = details.get("設置場所", "")
        contact = details.get("連絡先", "")
        maker = details.get("メーカー", "")
        model = details.get("型式", "")
        purpose = details.get("利用目的", "")
        equipment_id = _build_equipment_id(group, model)

        records.append(
            RawEquipment(
                equipment_id=equipment_id,
                name=name,
                category_general="機器分析センター",
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw=address_raw,
                external_use="要相談",
                conditions_note=_build_conditions_note(maker, model, purpose, contact),
                source_url=LIST_URL,
            )
        )

        if limit and len(records) >= limit:
            return records

    return records


def _extract_name(tag: Tag) -> str:
    text = clean_text(tag.get_text(" ", strip=True))
    if not text:
        return ""
    text = re.sub(r"^機種名\s*[:：]?", "", text).strip()
    return text.strip("　 ")


def _extract_details(table: Tag | None) -> dict[str, str]:
    if not table:
        return {}
    details: dict[str, str] = {}
    for row in table.select("tr"):
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all("td")]
        if len(cells) < 2:
            continue
        label = cells[0]
        value = cells[1]
        if label:
            details[label] = value
    return details


def _build_equipment_id(group: Tag, model: str) -> str:
    pdf_link = group.select_one('a[href$=".pdf"]')
    if pdf_link and pdf_link.get("href"):
        slug = urlparse(pdf_link["href"]).path.rsplit("/", 1)[-1].replace(".pdf", "")
        slug = unquote(slug)
        if slug:
            return f"KYUTECH-{slug}"
    if model:
        return f"KYUTECH-{model}"
    return ""


def _build_conditions_note(maker: str, model: str, purpose: str, contact: str) -> str:
    parts: list[str] = []
    if maker:
        parts.append(f"メーカー: {maker}")
    if model:
        parts.append(f"型式: {model}")
    if purpose:
        parts.append(f"利用目的: {purpose}")
    if contact:
        parts.append(f"連絡先: {contact}")
    return " / ".join(parts)
