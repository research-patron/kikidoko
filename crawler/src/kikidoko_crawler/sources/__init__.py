from __future__ import annotations

from typing import Callable

from ..models import RawEquipment
from .aist import fetch_aist_records
from .hokudai import fetch_hokudai_records
from .ims import fetch_ims_records
from .kyoto import fetch_kyoto_records
from .kyushu import fetch_kyushu_records
from .nagoya import fetch_nagoya_records
from .niigata import fetch_niigata_records
from .nims import fetch_nims_records
from .riken import fetch_riken_records
from .tmd import fetch_tmd_records
from .tohoku import fetch_tohoku_records
from .tsukuba import fetch_tsukuba_records
from .utokyo import fetch_utokyo_records

SourceHandler = Callable[[int, int], list[RawEquipment]]

SOURCE_HANDLERS: dict[str, SourceHandler] = {
    "aist": fetch_aist_records,
    "riken": fetch_riken_records,
    "hokudai": fetch_hokudai_records,
    "ims": fetch_ims_records,
    "kyoto": fetch_kyoto_records,
    "kyushu": fetch_kyushu_records,
    "nagoya": fetch_nagoya_records,
    "niigata": fetch_niigata_records,
    "nims": fetch_nims_records,
    "tohoku": fetch_tohoku_records,
    "utokyo": fetch_utokyo_records,
    "tsukuba": fetch_tsukuba_records,
    "tmd": fetch_tmd_records,
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
    for key in SOURCE_HANDLERS.keys():
        remaining = 0 if limit == 0 else max(limit - len(records), 0)
        records.extend(SOURCE_HANDLERS[key](timeout, remaining))
        if limit and len(records) >= limit:
            return records
    return records


__all__ = ["available_sources", "fetch_records"]
