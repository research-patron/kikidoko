from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

AIST_PORTAL_URL = "https://www.aist.go.jp/aist_j/business/alliance/orp/index.html"
TIA_BASE_URL = "https://tia-kyoyo.jp"
TIA_LIST_URL = f"{TIA_BASE_URL}/object.php"
TIA_FACILITY_IDS = [1, 2, 3, 4]

EQUIPMENT_ID_PATTERN = re.compile(
    r"^(?:[A-Z]{1,5}\d{2,4}[A-Z]?|[A-Z]{1,5}-\d{2,4}[A-Z]?|[A-Z]{1,3}\d{2}-\d{2,3}[A-Z]?)$"
)
LABEL_ID_PATTERN = re.compile(r"^【(?P<id>[^】]+)】\s*(?P<name>.*)$")


def fetch_aist_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    records: list[RawEquipment] = []
    seen: set[str] = set()
    default_address = _fetch_contact_address(timeout)
    for facility_id in TIA_FACILITY_IDS:
        list_url = f"{TIA_LIST_URL}?f={facility_id}"
        response = requests.get(list_url, timeout=timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for record in _extract_records_from_list(
            soup, list_url, default_address
        ):
            dedupe_hint = record.equipment_id or record.name
            if dedupe_hint and dedupe_hint in seen:
                continue
            if dedupe_hint:
                seen.add(dedupe_hint)
            records.append(record)
            if limit and len(records) >= limit:
                return records
    return records


def _extract_records_from_list(
    soup: BeautifulSoup, list_url: str, default_address: str
) -> list[RawEquipment]:
    table = soup.find("table")
    if not table:
        return []
    rows = table.find_all("tr")
    records: list[RawEquipment] = []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        name_raw = clean_text(cells[0].get_text(" ", strip=True))
        category = clean_text(cells[1].get_text(" ", strip=True))
        if not name_raw:
            continue
        equipment_id, name = _split_equipment_label(name_raw)
        source_url = list_url
        link = cells[0].find("a")
        if link and link.get("href"):
            source_url = urljoin(list_url, link["href"])
        records.append(
            RawEquipment(
                equipment_id=f"AIST-{equipment_id}" if equipment_id else "",
                name=name or name_raw,
                category_general=category,
                org_name="産業技術総合研究所",
                external_use="要相談",
                address_raw=default_address,
                source_url=source_url,
            )
        )
    return records


def _split_equipment_label(text: str) -> tuple[str, str]:
    match = LABEL_ID_PATTERN.match(text)
    if match:
        equipment_id = clean_text(match.group("id"))
        name = clean_text(match.group("name"))
        if equipment_id and _is_equipment_id(equipment_id):
            return equipment_id, name
    return "", text


def _is_equipment_id(value: str) -> bool:
    return bool(EQUIPMENT_ID_PATTERN.match(value))


def _fetch_contact_address(timeout: int) -> str:
    response = requests.get(AIST_PORTAL_URL, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for paragraph in soup.find_all("p"):
        text = clean_text(paragraph.get_text(" ", strip=True))
        if "〒" in text:
            text = text.split("Eメール", 1)[0].strip()
            if "茨城県" in text:
                return text
    return ""
