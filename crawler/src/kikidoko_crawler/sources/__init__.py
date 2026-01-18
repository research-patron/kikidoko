from __future__ import annotations

from typing import Callable

from ..models import RawEquipment
from .aist import fetch_aist_records
from .hokudai import fetch_hokudai_records
from .kyushu import fetch_kyushu_records

SourceHandler = Callable[[int, int], list[RawEquipment]]

SOURCE_HANDLERS: dict[str, SourceHandler] = {
    "hokudai": fetch_hokudai_records,
    "aist": fetch_aist_records,
    "kyushu": fetch_kyushu_records,
}


def available_sources() -> list[str]:
    return sorted(list(SOURCE_HANDLERS.keys()) + ["all"])


def fetch_records(source: str, timeout: int, limit: int = 0) -> list[RawEquipment]:
    if source == "all":
        return _fetch_all(timeout, limit)
    if source not in SOURCE_HANDLERS:
        raise ValueError(f"Unknown source: {source}")
    return SOURCE_HANDLERS[source](timeout, limit)


def _fetch_all(timeout: int, limit: int) -> list[RawEquipment]:
    records: list[RawEquipment] = []
    for key in sorted(SOURCE_HANDLERS.keys()):
        remaining = 0 if limit == 0 else max(limit - len(records), 0)
        records.extend(SOURCE_HANDLERS[key](timeout, remaining))
        if limit and len(records) >= limit:
            return records
    return records


__all__ = ["available_sources", "fetch_records"]
