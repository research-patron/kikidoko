from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.med.oita-u.ac.jp/biolabo/setubi.html"
ORG_NAME = "大分大学 医学部 バイオラボセンター"
PREFECTURE = "大分県"
CATEGORY_GENERAL = "バイオラボセンター"


def fetch_oita_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    table = soup.find("table")
    if not table:
        return []

    records: list[RawEquipment] = []
    for row in table.find_all("tr"):
        raw_cells = row.find_all(["th", "td"])
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in raw_cells]
        if not cells:
            continue
        if any("機器" in cell for cell in cells) and any("メーカー" in cell for cell in cells):
            continue
        if len(cells) < 3:
            continue
        name = cells[0]
        if not name:
            continue
        maker = cells[1] if len(cells) > 1 else ""
        count = cells[2] if len(cells) > 2 else ""
        note = cells[3] if len(cells) > 3 else ""

        records.append(
            RawEquipment(
                name=name,
                category_general=CATEGORY_GENERAL,
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw="大分大学 医学部",
                external_use="要相談",
                conditions_note=_build_conditions_note(maker, count, note),
                source_url=LIST_URL,
            )
        )

        if limit and len(records) >= limit:
            return records

    return records


def _build_conditions_note(maker: str, count: str, note: str) -> str:
    parts: list[str] = []
    if maker:
        parts.append(f"メーカー: {maker}")
    if count:
        parts.append(f"台数: {count}")
    if note:
        parts.append(f"備考: {note}")
    return " / ".join(parts)
