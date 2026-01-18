from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.imass.nagoya-u.ac.jp/equipment"
ORG_NAME = "名古屋大学 未来材料・システム研究所"
PREFECTURE = "愛知県"
CATEGORY_GENERAL = "共通機器"


def fetch_nagoya_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")

    tables = soup.find_all("table", class_="l-table-machine")
    if not tables:
        tables = soup.find_all("table")

    records: list[RawEquipment] = []
    for table in tables:
        location = _extract_location_heading(table)
        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue
            equipment_id = _format_equipment_id(
                clean_text(cells[0].get_text(" ", strip=True))
            )
            name = clean_text(cells[1].get_text(" ", strip=True))
            if not name:
                continue
            contact = clean_text(cells[2].get_text(" ", strip=True))
            fee_value = clean_text(cells[3].get_text(" ", strip=True))
            remarks = (
                clean_text(cells[4].get_text(" ", strip=True)) if len(cells) > 4 else ""
            )
            fee_note = _build_fee_note(fee_value, remarks)
            conditions_note = _build_conditions_note(contact)
            address_raw = _build_address(location)

            records.append(
                RawEquipment(
                    equipment_id=equipment_id,
                    name=name,
                    category_general=CATEGORY_GENERAL,
                    org_name=ORG_NAME,
                    prefecture=PREFECTURE,
                    address_raw=address_raw,
                    fee_note=fee_note,
                    conditions_note=conditions_note,
                    source_url=LIST_URL,
                )
            )
            if limit and len(records) >= limit:
                return records

    return records


def _extract_location_heading(table: BeautifulSoup) -> str:
    heading = table.find_previous(["h2", "h3", "h4"])
    if not heading:
        return ""
    text = clean_text(heading.get_text(" ", strip=True))
    return re.sub(r"\s*設置\s*$", "", text)


def _build_address(location: str) -> str:
    if not location:
        return "名古屋大学"
    return f"名古屋大学 {location}"


def _build_fee_note(fee_value: str, remarks: str) -> str:
    parts: list[str] = []
    if not fee_value:
        parts.append("料金要相談")
    else:
        if "円" not in fee_value and re.search(r"\d", fee_value):
            parts.append(f"{fee_value}円/時間")
        else:
            parts.append(fee_value)
    if remarks:
        parts.append(f"備考: {remarks}")
    return " / ".join(parts)


def _build_conditions_note(contact: str) -> str:
    if not contact:
        return ""
    return f"担当者: {contact}"


def _format_equipment_id(raw_id: str) -> str:
    if not raw_id:
        return ""
    safe_id = re.sub(r"[^0-9A-Za-z-]", "-", raw_id)
    return f"NAGOYA-IMASS-{safe_id}"
