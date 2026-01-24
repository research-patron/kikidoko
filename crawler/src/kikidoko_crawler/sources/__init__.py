from __future__ import annotations

from typing import Callable

from ..models import RawEquipment
from .aist import fetch_aist_records
from .chiba import fetch_chiba_records
from .ehime import fetch_ehime_records
from .fukui import fetch_fukui_records
from .gifu import fetch_gifu_records
from .gunma import fetch_gunma_records
from .hiroshima import fetch_hiroshima_records
from .hokudai import fetch_hokudai_records
from .ibaraki import fetch_ibaraki_records
from .ims import fetch_ims_records
from .iwate import fetch_iwate_records
from .jaist import fetch_jaist_records
from .kanazawa import fetch_kanazawa_records
from .kagoshima import fetch_kagoshima_records
from .kek import fetch_kek_records
from .kitami import fetch_kitami_records
from .kobe import fetch_kobe_records
from .kumamoto import fetch_kumamoto_records
from .kyoto import fetch_kyoto_records
from .kyutech import fetch_kyutech_records
from .kyushu import fetch_kyushu_records
from .mie import fetch_mie_records
from .miyazaki import fetch_miyazaki_records
from .muroran import fetch_muroran_records
from .nagaoka import fetch_nagaoka_records
from .nagasaki import fetch_nagasaki_records
from .nagoya import fetch_nagoya_records
from .naist import fetch_naist_records
from .nitech import fetch_nitech_records
from .niigata import fetch_niigata_records
from .nims import fetch_nims_records
from .obihiro import fetch_obihiro_records
from .ochanomizu import fetch_ochanomizu_records
from .oita import fetch_oita_records
from .okayama import fetch_okayama_records
from .oist import fetch_oist_records
from .osaka import fetch_osaka_records
from .riken import fetch_riken_records
from .saga import fetch_saga_records
from .shimane import fetch_shimane_records
from .shinshu import fetch_shinshu_records
from .tmd import fetch_tmd_records
from .tohoku import fetch_tohoku_records
from .tsukuba import fetch_tsukuba_records
from .utokyo import fetch_utokyo_records

SourceHandler = Callable[[int, int], list[RawEquipment]]

SOURCE_HANDLERS: dict[str, SourceHandler] = {
    "aist": fetch_aist_records,
    "chiba": fetch_chiba_records,
    "ehime": fetch_ehime_records,
    "fukui": fetch_fukui_records,
    "gifu": fetch_gifu_records,
    "gunma": fetch_gunma_records,
    "hiroshima": fetch_hiroshima_records,
    "riken": fetch_riken_records,
    "hokudai": fetch_hokudai_records,
    "ibaraki": fetch_ibaraki_records,
    "ims": fetch_ims_records,
    "iwate": fetch_iwate_records,
    "jaist": fetch_jaist_records,
    "kanazawa": fetch_kanazawa_records,
    "kagoshima": fetch_kagoshima_records,
    "kek": fetch_kek_records,
    "kitami": fetch_kitami_records,
    "kobe": fetch_kobe_records,
    "kumamoto": fetch_kumamoto_records,
    "kyoto": fetch_kyoto_records,
    "kyutech": fetch_kyutech_records,
    "kyushu": fetch_kyushu_records,
    "mie": fetch_mie_records,
    "miyazaki": fetch_miyazaki_records,
    "muroran": fetch_muroran_records,
    "nagaoka": fetch_nagaoka_records,
    "nagasaki": fetch_nagasaki_records,
    "nagoya": fetch_nagoya_records,
    "naist": fetch_naist_records,
    "nitech": fetch_nitech_records,
    "niigata": fetch_niigata_records,
    "nims": fetch_nims_records,
    "obihiro": fetch_obihiro_records,
    "ochanomizu": fetch_ochanomizu_records,
    "oita": fetch_oita_records,
    "okayama": fetch_okayama_records,
    "oist": fetch_oist_records,
    "osaka": fetch_osaka_records,
    "saga": fetch_saga_records,
    "shimane": fetch_shimane_records,
    "shinshu": fetch_shinshu_records,
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
