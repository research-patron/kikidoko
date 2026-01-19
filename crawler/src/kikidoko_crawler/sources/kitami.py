from __future__ import annotations

import csv
from io import StringIO

import requests

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://www.iac.kitami-it.ac.jp/Device_summary/list.html"
CSV_URL = "https://www.iac.kitami-it.ac.jp/Device_summary/data/kikilist.csv"
ORG_NAME = "北見工業大学 共用設備センター"
PREFECTURE = "北海道"


def fetch_kitami_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(CSV_URL, timeout=timeout)
    response.raise_for_status()
    text = response.content.decode("utf-8-sig", errors="replace")
    reader = csv.reader(StringIO(text))
    rows = list(reader)
    if not rows:
        return []

    records: list[RawEquipment] = []
    seen_names: set[str] = set()
    for row in rows[1:]:
        name = clean_text(_get(row, 3))
        if not name:
            continue

        equipment_id = clean_text(_get(row, 0))
        category_general = clean_text(_get(row, 1))
        category_detail = clean_text(_get(row, 2))
        maker = clean_text(_get(row, 4))
        model = clean_text(_get(row, 5))
        manage_type = clean_text(_get(row, 7))
        building = clean_text(_get(row, 8))
        room = clean_text(_get(row, 9))
        manager = clean_text(_get(row, 10))
        manager_ext = clean_text(_get(row, 11))
        operator = clean_text(_get(row, 12))
        operator_ext = clean_text(_get(row, 13))
        open_days = clean_text(_get(row, 14))
        open_time = clean_text(_get(row, 15))
        notice = clean_text(_get(row, 16))
        note = clean_text(_get(row, 17))

        if manage_type == "帯広" or "帯広畜産大学" in notice or "詳細は下記リンク先" in building:
            continue

        display_name = _build_display_name(name, model, equipment_id, seen_names)

        records.append(
            RawEquipment(
                equipment_id=_format_equipment_id(equipment_id),
                name=display_name,
                category_general=category_general,
                category_detail=category_detail,
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                address_raw=_build_address(building, room),
                conditions_note=_build_conditions_note(
                    maker,
                    model,
                    manage_type,
                    manager,
                    manager_ext,
                    operator,
                    operator_ext,
                    open_days,
                    open_time,
                    notice,
                    note,
                ),
                source_url=LIST_URL,
            )
        )
        if limit and len(records) >= limit:
            return records

    return records


def _get(row: list[str], index: int) -> str:
    return row[index] if index < len(row) else ""


def _format_equipment_id(value: str) -> str:
    if not value:
        return ""
    return f"KITAMI-{value}"


def _build_display_name(
    name: str, model: str, equipment_id: str, seen: set[str]
) -> str:
    display_name = name
    if model and model not in display_name:
        display_name = f"{display_name} ({model})"
    if display_name in seen and equipment_id:
        display_name = f"{display_name} [{equipment_id}]"
    seen.add(display_name)
    return display_name


def _build_address(building: str, room: str) -> str:
    parts = [part for part in (building, room) if part]
    if not parts:
        return "北見工業大学"
    return f"北見工業大学 {' '.join(parts)}"


def _build_conditions_note(
    maker: str,
    model: str,
    manage_type: str,
    manager: str,
    manager_ext: str,
    operator: str,
    operator_ext: str,
    open_days: str,
    open_time: str,
    notice: str,
    note: str,
) -> str:
    parts: list[str] = []
    if maker:
        parts.append(f"メーカー: {maker}")
    if model:
        parts.append(f"型式: {model}")
    if manage_type:
        parts.append(f"管理形態: {manage_type}")
    if manager:
        contact = f"{manager} ({manager_ext})" if manager_ext else manager
        parts.append(f"機器管理者: {contact}")
    if operator:
        contact = f"{operator} ({operator_ext})" if operator_ext else operator
        parts.append(f"機器担当者: {contact}")
    if open_days:
        parts.append(f"開放曜日: {open_days}")
    if open_time:
        parts.append(f"開放時間帯: {open_time}")
    if notice:
        parts.append(f"お知らせ: {notice}")
    if note:
        parts.append(f"備考: {note}")
    return " / ".join(parts)
