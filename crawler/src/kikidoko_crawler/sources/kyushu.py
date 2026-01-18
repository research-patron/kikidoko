from __future__ import annotations

from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://bunseki.kyushu-u.ac.jp/bunseki/equipmentlist"


def fetch_kyushu_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    records: list[RawEquipment] = []
    for section in soup.select("div.kikilist"):
        section_title = ""
        header = section.find("h2")
        if header:
            section_title = clean_text(header.get_text(" ", strip=True))
        org_name = "九州大学"
        if section_title:
            org_name = f"九州大学 {section_title}"

        for table in section.find_all("table"):
            for row in table.select("tbody tr"):
                cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all("td")]
                if not cells:
                    continue
                anchor = row.find("a")
                name = clean_text(anchor.get_text(" ", strip=True)) if anchor else cells[0]
                if not name:
                    continue

                source_url = LIST_URL
                if anchor and anchor.get("href"):
                    source_url = urljoin(LIST_URL, anchor["href"])

                location = cells[1] if len(cells) > 1 else ""
                contact = cells[2] if len(cells) > 2 else ""
                note = cells[3] if len(cells) > 3 else ""

                notes = []
                if contact:
                    notes.append(f"担当者: {contact}")
                if note:
                    notes.append(note)
                conditions_note = " / ".join(notes)

                equipment_id = ""
                if anchor and anchor.get("href"):
                    slug = urlparse(source_url).path.rsplit("/", 1)[-1].replace(".html", "")
                    if slug:
                        equipment_id = f"KYUSHU-{slug}"

                records.append(
                    RawEquipment(
                        equipment_id=equipment_id,
                        name=name,
                        org_name=org_name,
                        prefecture="福岡県",
                        address_raw=location,
                        external_use="要相談",
                        conditions_note=conditions_note,
                        source_url=source_url,
                    )
                )

                if limit and len(records) >= limit:
                    return records

    return records
