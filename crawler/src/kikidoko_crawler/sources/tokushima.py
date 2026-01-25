from __future__ import annotations

from typing import Any
import re

import requests
import urllib3
from urllib3.exceptions import InsecureRequestWarning

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "https://kiki.st.tokushima-u.ac.jp/machine/index.html"
DATA_URL = "https://kiki.st.tokushima-u.ac.jp/js/machine-data.json"
ORG_NAME = "徳島大学 地域協働技術センター"
PREFECTURE = "徳島県"
TAG_PATTERN = re.compile(r"<[^>]+>")


def fetch_tokushima_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    urllib3.disable_warnings(InsecureRequestWarning)
    response = requests.get(DATA_URL, timeout=timeout, verify=False)
    response.raise_for_status()
    data: dict[str, Any] = response.json()

    records: list[RawEquipment] = []
    seen: set[str] = set()
    for key, item in data.items():
        record = _build_record(key, item)
        if not record:
            continue
        if record.equipment_id in seen:
            continue
        seen.add(record.equipment_id)
        records.append(record)
        if limit and len(records) >= limit:
            return records
    return records


def _build_record(key: str, item: dict[str, Any]) -> RawEquipment | None:
    name = _strip_html(item.get("name", ""))
    if not name:
        return None

    category = _strip_html(item.get("category", ""))
    spec = item.get("spec") or []
    maker = _strip_html(spec[0]) if len(spec) > 0 else ""
    model = _strip_html(spec[1]) if len(spec) > 1 else ""
    purpose = _clean_list(item.get("purpose"))
    feature = _clean_list(item.get("feature"))
    note = _clean_list(item.get("note"))
    location = _strip_html(item.get("location", ""))

    return RawEquipment(
        equipment_id=f"TOKUSHIMA-{key}",
        name=name,
        category_general=category,
        org_name=ORG_NAME,
        prefecture=PREFECTURE,
        address_raw=location,
        conditions_note=_build_conditions_note(maker, model, purpose, feature, note),
        source_url=LIST_URL,
    )


def _clean_list(values: Any) -> list[str]:
    if not values:
        return []
    cleaned = [_strip_html(value) for value in values if value]
    return [value for value in cleaned if value and value != "-"]


def _strip_html(value: str) -> str:
    if not value:
        return ""
    text = TAG_PATTERN.sub(" ", value)
    return clean_text(text)


def _build_conditions_note(
    maker: str, model: str, purpose: list[str], feature: list[str], note: list[str]
) -> str:
    parts: list[str] = []
    if maker:
        parts.append(f"メーカー: {maker}")
    if model:
        parts.append(f"型式: {model}")
    if purpose:
        parts.append(f"用途: {' / '.join(purpose)}")
    if feature:
        parts.append(f"特徴: {' / '.join(feature)}")
    if note:
        parts.append(f"備考: {' / '.join(note)}")
    return " / ".join(parts)
