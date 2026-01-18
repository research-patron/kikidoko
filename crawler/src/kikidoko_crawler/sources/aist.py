from __future__ import annotations

import io
import re
from typing import Iterable
from urllib.parse import urljoin

import pdfplumber
import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text, normalize_label

AIST_PORTAL_URL = "https://www.aist.go.jp/aist_j/business/alliance/orp/index.html"
AIST_BASE_URL = "https://www.aist.go.jp"

EQUIPMENT_ID_PATTERN = re.compile(
    r"^(?:[A-Z]{1,5}\d{2,4}[A-Z]?|[A-Z]{1,5}-\d{2,4}[A-Z]?|[A-Z]{1,3}\d{2}-\d{2,3}[A-Z]?)$"
)


def fetch_aist_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    records: list[RawEquipment] = []
    seen: set[str] = set()
    for pdf_url in _fetch_pdf_links(timeout):
        for record in _extract_records_from_pdf(pdf_url, timeout):
            dedupe_hint = record.equipment_id or record.name
            if dedupe_hint and dedupe_hint in seen:
                continue
            if dedupe_hint:
                seen.add(dedupe_hint)
            records.append(record)
            if limit and len(records) >= limit:
                return records
    return records


def _fetch_pdf_links(timeout: int) -> list[str]:
    response = requests.get(AIST_PORTAL_URL, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    links = []
    for anchor in soup.select("a[href]"):
        href = anchor["href"]
        if "/pdf/aist_j/business/orp/list/" not in href:
            continue
        links.append(urljoin(AIST_BASE_URL, href))
    return sorted(set(links))


def _extract_records_from_pdf(pdf_url: str, timeout: int) -> Iterable[RawEquipment]:
    response = requests.get(pdf_url, timeout=timeout)
    response.raise_for_status()
    with pdfplumber.open(io.BytesIO(response.content)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                yield from _extract_records_from_table(table, pdf_url)


def _extract_records_from_table(
    table: list[list[str | None]], pdf_url: str
) -> Iterable[RawEquipment]:
    if not table:
        return []

    header_row = table[0]
    header_labels = [_normalize_header(cell) for cell in header_row]
    id_index = _find_header_index(header_labels, ["装置番号"])
    name_index = _find_header_index(header_labels, ["施設等名称", "施設名称", "装置名"])
    location_index = _find_header_index(header_labels, ["設置場所"])
    note_index = _find_header_index(header_labels, ["備考"])
    category_index = _find_header_index(header_labels, ["装置分類"])

    manufacturer_index, model_index = _find_subheader_indexes(table[:3])
    if (
        category_index is None
        and manufacturer_index is None
        and header_labels
        and header_labels[-1] == ""
    ):
        category_index = len(header_labels) - 1

    records: list[RawEquipment] = []
    for row in table[1:]:
        cells = [_clean_cell(value) for value in row]
        if not any(cells):
            continue
        if _is_header_row(cells):
            continue

        equipment_id, name = _extract_id_and_name(cells, id_index, name_index)
        if not equipment_id or not _is_equipment_id(equipment_id):
            continue
        if not name:
            continue

        category_general = _get_cell(cells, category_index)
        note_value = _get_cell(cells, note_index)
        location_value = _get_cell(cells, location_index)

        address_raw = location_value
        if not address_raw and note_value and _looks_like_location(note_value):
            address_raw = note_value

        notes = []
        if note_value and note_value != address_raw:
            notes.append(f"備考: {note_value}")

        manufacturer = _get_cell(cells, manufacturer_index)
        if manufacturer:
            notes.append(f"メーカー: {manufacturer}")

        model = _get_cell(cells, model_index)
        if model:
            notes.append(f"型番: {model}")

        conditions_note = " / ".join(notes)

        records.append(
            RawEquipment(
                equipment_id=f"AIST-{equipment_id}",
                name=name,
                category_general=category_general,
                org_name="産業技術総合研究所",
                external_use="要相談",
                address_raw=address_raw,
                conditions_note=conditions_note,
                source_url=pdf_url,
            )
        )

    return records


def _normalize_header(value: str | None) -> str:
    if value is None:
        return ""
    return normalize_label(value)


def _find_header_index(labels: list[str], targets: list[str]) -> int | None:
    for target in targets:
        if target in labels:
            return labels.index(target)
    return None


def _find_subheader_indexes(
    rows: list[list[str | None]],
) -> tuple[int | None, int | None]:
    manufacturer_index = None
    model_index = None
    for row in rows:
        labels = [_normalize_header(cell) for cell in row]
        if "メーカー名" in labels:
            manufacturer_index = labels.index("メーカー名")
        if "型番" in labels:
            model_index = labels.index("型番")
    return manufacturer_index, model_index


def _is_header_row(cells: list[str]) -> bool:
    header_keywords = {"装置番号", "施設等名称", "施設名称", "装置名", "メーカー名", "型番"}
    return any(cell in header_keywords for cell in cells)


def _extract_id_and_name(
    cells: list[str], id_index: int | None, name_index: int | None
) -> tuple[str, str]:
    equipment_id = _get_cell(cells, id_index)
    name = _get_cell(cells, name_index)

    if not equipment_id:
        for idx, cell in enumerate(cells):
            if _is_equipment_id(cell):
                equipment_id = cell
                if not name and idx + 1 < len(cells):
                    name = cells[idx + 1]
                break

    return equipment_id, name


def _get_cell(cells: list[str], index: int | None) -> str:
    if index is None or index >= len(cells):
        return ""
    return cells[index]


def _clean_cell(value: str | None) -> str:
    if value is None:
        return ""
    return clean_text(value.replace("\n", " "))


def _is_equipment_id(value: str) -> bool:
    return bool(EQUIPMENT_ID_PATTERN.match(value))


def _looks_like_location(value: str) -> bool:
    return bool(
        re.search(r"(棟|室|クリーンルーム|イエロールーム|フロア|\\d+F)", value)
    )
