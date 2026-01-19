from __future__ import annotations

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www2.kek.jp/imss/pf/eng/apparatus/bl/stationlist.html"
ORG_NAME = "高エネルギー加速器研究機構 Photon Factory"
PREFECTURE = "茨城県"
CATEGORY_GENERAL = "ビームライン"


def fetch_kek_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.find("table")
    if not table:
        return []

    records: list[RawEquipment] = []
    for row in table.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 5:
            continue
        if clean_text(cells[0].get_text(" ", strip=True)) == "BL":
            continue

        bl = clean_text(cells[0].get_text(" ", strip=True))
        ls = clean_text(cells[1].get_text(" ", strip=True))
        org = clean_text(cells[2].get_text(" ", strip=True))
        station = clean_text(cells[3].get_text(" ", strip=True))
        staff = clean_text(cells[4].get_text(" ", strip=True))

        name = " ".join([part for part in (bl, station) if part])
        if not name:
            continue

        records.append(
            RawEquipment(
                name=name,
                category_general=CATEGORY_GENERAL,
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw=ORG_NAME,
                conditions_note=_build_conditions_note(ls, org, staff),
                source_url=_extract_source_url(row),
            )
        )
        if limit and len(records) >= limit:
            return records

    return records


def _extract_source_url(row: BeautifulSoup) -> str:
    for anchor in row.find_all("a", href=True):
        href = anchor.get("href", "")
        if not href or href.startswith("mailto:"):
            continue
        return urljoin(LIST_URL, href)
    return LIST_URL


def _build_conditions_note(ls: str, org: str, staff: str) -> str:
    parts: list[str] = []
    if ls:
        parts.append(f"LS: {ls}")
    if org:
        parts.append(f"Org: {org}")
    if staff:
        parts.append(f"Staff: {staff}")
    return " / ".join(parts)
