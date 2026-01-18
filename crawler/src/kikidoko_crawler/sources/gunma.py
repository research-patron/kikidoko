from __future__ import annotations

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text

LIST_URL = "http://www.trcia.gunma-u.ac.jp/inst/"
ORG_NAME = "群馬大学 コアファシリティ総合センター エンジニアリング分野"
PREFECTURE = "群馬県"


def fetch_gunma_records(timeout: int, limit: int = 0) -> list[RawEquipment]:
    response = requests.get(LIST_URL, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")

    records: list[RawEquipment] = []
    for anchor in soup.select("div.kikiName a[href]"):
        name = clean_text(anchor.get_text(" ", strip=True))
        if not name:
            continue
        source_url = urljoin(LIST_URL, anchor["href"])
        records.append(
            RawEquipment(
                name=name,
                org_name=ORG_NAME,
                prefecture=PREFECTURE,
                source_url=source_url,
            )
        )
        if limit and len(records) >= limit:
            return records

    return records
