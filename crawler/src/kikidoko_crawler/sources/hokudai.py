from __future__ import annotations

from typing import Any

import requests

from ..models import RawEquipment
from ..utils import clean_text

BASE_URL = "https://www.gfc.hokudai.ac.jp"
LIST_ENDPOINT = f"{BASE_URL}/system/gfc_apparatus_list/list"


def fetch_hokudai_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    session = requests.Session()
    records: list[RawEquipment] = []
    page_size = 200
    start_index = 0
    total_count: int | None = None

    while True:
        payload = {
            "jtStartIndex": start_index,
            "jtPageSize": page_size,
            "jtSorting": "item_name ASC, item_id ASC",
        }
        response = session.post(LIST_ENDPOINT, data=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        if data.get("Result") != "OK":
            raise RuntimeError(f"Hokudai list returned {data.get('Result')}")

        total_count = data.get("TotalRecordCount", total_count)
        page_records = data.get("Records", [])
        if start_index == 0 and total_count is not None:
            if len(page_records) >= total_count:
                for item in page_records:
                    records.append(_build_record(item))
                    if limit and len(records) >= limit:
                        return records
                return records

        for item in page_records:
            records.append(_build_record(item))
            if limit and len(records) >= limit:
                return records

        start_index += page_size
        if total_count is None or start_index >= total_count:
            break

    return records


def _build_record(item: dict[str, Any]) -> RawEquipment:
    item_id = clean_text(str(item.get("item_id", "")))
    item_no = clean_text(str(item.get("item_no", "")))
    item_name = clean_text(str(item.get("item_name", "")))
    category_general = clean_text(str(item.get("category_1", "")))
    category_detail = clean_text(str(item.get("category_2", "")))
    build_name = clean_text(str(item.get("build_name", "")))
    floor_name = clean_text(str(item.get("floor_name", "")))
    location = clean_text(" ".join([value for value in (build_name, floor_name) if value]))

    local_show = str(item.get("local_show", ""))
    gov_show = str(item.get("gov_show", ""))
    cop_show = str(item.get("cop_show", ""))
    external_use = _classify_external_use(local_show, gov_show, cop_show)

    equipment_id = ""
    if item_no:
        equipment_id = f"HOKUDAI-{item_no}"
    elif item_id:
        equipment_id = f"HOKUDAI-{item_id}"

    source_url = ""
    if item_id:
        source_url = f"{BASE_URL}/apparatus_list/detail?item_id={item_id}"

    address_raw = location or "北海道大学"

    return RawEquipment(
        equipment_id=equipment_id,
        name=item_name,
        category_general=category_general,
        category_detail=category_detail,
        org_name="北海道大学",
        prefecture="北海道",
        address_raw=address_raw,
        external_use=external_use,
        source_url=source_url,
    )


def _classify_external_use(local_show: str, gov_show: str, cop_show: str) -> str:
    if gov_show == "1" or cop_show == "1":
        return "可"
    if local_show == "1":
        return "不可"
    return "不明"
