from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://asrc.w3.kanazawa-u.ac.jp/experiment/machine/share/"
ORG_NAME = "金沢大学 疾患モデル総合研究センター 機器分析研究施設"
PREFECTURE = "石川県"
CATEGORY_GENERAL = "機器分析研究施設"
CATEGORY_DETAIL = "共同利用機器"


def fetch_kanazawa_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.find("table")
    if not table:
        return []

    records: list[RawEquipment] = []
    for row in table.find_all("tr"):
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
        if len(cells) < 4:
            continue
        if cells[0] in {"", "担当者"} or cells[1] == "機器名":
            continue

        equipment_id = _format_equipment_id(cells[0])
        name = cells[1]
        if not name:
            continue
        measurement = cells[2] if len(cells) > 2 else ""
        contact = cells[3] if len(cells) > 3 else ""
        phone = cells[4] if len(cells) > 4 else ""

        records.append(
            RawEquipment(
                equipment_id=equipment_id,
                name=name,
                category_general=CATEGORY_GENERAL,
                category_detail=CATEGORY_DETAIL,
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw="金沢大学 疾患モデル総合研究センター",
                conditions_note=_build_conditions_note(measurement, contact, phone),
                source_url=LIST_URL,
            )
        )
        if limit and len(records) >= limit:
            return records

    return records


def _format_equipment_id(value: str) -> str:
    if not value:
        return ""
    return f"KANAZAWA-{value}"


def _build_conditions_note(measurement: str, contact: str, phone: str) -> str:
    parts: list[str] = []
    if measurement:
        parts.append(f"測定区分: {measurement}")
    if contact:
        parts.append(f"申込先: {contact}")
    if phone:
        parts.append(f"電話: {phone}")
    return " / ".join(parts)
