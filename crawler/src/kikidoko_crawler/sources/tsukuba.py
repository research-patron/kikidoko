from __future__ import annotations

from .table_utils import TableConfig, fetch_table_records


def fetch_tsukuba_records(timeout: int, limit: int = 0):
    config = TableConfig(
        key="tsukuba",
        org_name="筑波大学",
        url="https://openfacility.sec.tsukuba.ac.jp/public_eq/front.php?cont=eq_index",
        link_patterns=("cont=eq_index",),
    )
    return fetch_table_records(config, timeout, limit)

