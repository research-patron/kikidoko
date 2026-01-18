from __future__ import annotations

from .table_utils import TableConfig, fetch_table_records


def fetch_tmd_records(timeout: int, limit: int = 0):
    config = TableConfig(
        key="tmd",
        org_name="東京医科歯科大学",
        url="https://www.tmd.ac.jp/rcmd/equipment/",
        category_hint="研究設備",
    )
    return fetch_table_records(config, timeout, limit)

