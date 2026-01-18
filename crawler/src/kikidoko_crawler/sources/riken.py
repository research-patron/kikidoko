from __future__ import annotations

from .table_utils import TableConfig, fetch_table_records


def fetch_riken_records(timeout: int, limit: int = 0):
    config = TableConfig(
        key="riken",
        org_name="理化学研究所",
        url="https://www.innovation-riken.jp/riken-facilities/",
        category_hint="研究施設",
    )
    return fetch_table_records(config, timeout, limit)

