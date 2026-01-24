from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text, compute_dedupe_key

LIST_URL = "https://www.shimane-u.org/kiki.htm"
ORG_NAME = "島根大学 研究・学術情報本部 総合科学研究支援センター 遺伝子機能解析部門"
PREFECTURE = "島根県"
CATEGORY_GENERAL = "研究設備"


def fetch_shimane_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    soup = BeautifulSoup(response.text, "html.parser")

    records: list[RawEquipment] = []
    seen: set[str] = set()
    for table in soup.select('table[border="1"]'):
        rows = table.find_all("tr")
        if not rows:
            continue
        header_cells = [clean_text(cell.get_text(" ", strip=True)) for cell in rows[0].find_all("td")]
        if not _is_header_row(header_cells):
            continue

        current_category = ""
        for row in rows[1:]:
            cells = row.find_all("td")
            if not cells:
                continue
            texts = [clean_text(cell.get_text(" ", strip=True)) for cell in cells]
            if any(text in {"種別", "機器名", "機種", "設置場所"} for text in texts):
                continue
            if len(cells) == 4:
                current_category = texts[0]
                name, model, location = texts[1], texts[2], texts[3]
                link_cell = cells[1]
            elif len(cells) == 3:
                name, model, location = texts[0], texts[1], texts[2]
                link_cell = cells[0]
            else:
                continue
            if not name:
                continue

            source_url = _extract_link(link_cell) or LIST_URL
            equipment_id = _build_equipment_id(source_url, name, model, location)
            dedupe_key = equipment_id or f"{name}|{model}|{location}|{current_category}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            records.append(
                RawEquipment(
                    equipment_id=equipment_id,
                    name=name,
                    category_general=CATEGORY_GENERAL,
                    category_detail=current_category,
                    org_name=ORG_NAME,
                    prefecture=PREFECTURE,
                    address_raw=location,
                    conditions_note=_build_conditions_note(model),
                    source_url=source_url,
                )
            )
            if limit and len(records) >= limit:
                return records

    return records


def _is_header_row(cells: list[str]) -> bool:
    if len(cells) < 4:
        return False
    header_text = " ".join(cells)
    return all(label in header_text for label in ("種別", "機器名", "機種", "設置場所"))


def _extract_link(cell: BeautifulSoup) -> str:
    anchor = cell.find("a", href=True)
    if not anchor:
        return ""
    return urljoin(LIST_URL, anchor["href"])


def _build_conditions_note(model: str) -> str:
    if not model:
        return ""
    return f"機種: {model}"


def _build_equipment_id(detail_url: str, name: str, model: str, location: str) -> str:
    parsed = urlparse(detail_url)
    slug = parsed.path.rstrip("/").split("/")[-1]
    slug = slug.replace(".htm", "").replace(".html", "")
    if slug and slug != "kiki":
        return f"SHIMANE-{slug}"
    fallback = re.sub(r"[^A-Za-z0-9]+", "-", clean_text(name)).strip("-")
    if fallback:
        return f"SHIMANE-{fallback}"
    digest = compute_dedupe_key(name, model, location, detail_url)
    return f"SHIMANE-{digest}" if digest else ""
