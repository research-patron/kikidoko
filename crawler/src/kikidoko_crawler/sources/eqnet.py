from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..models import RawEquipment
from ..utils import clean_text, normalize_label


@dataclass
class EqnetListItem:
    equipment_id: str
    url: str
    name: str
    org_name: str


class EqnetCrawler:
    def __init__(
        self,
        list_url: str | None,
        detail_url_template: str | None,
        timeout: int = 20,
        logger=None,
    ) -> None:
        if not list_url and not detail_url_template:
            raise ValueError("EQNET_LIST_URL or EQNET_DETAIL_URL_TEMPLATE is required")
        self.list_url = list_url
        self.detail_url_template = detail_url_template
        self.timeout = timeout
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
        )

    def crawl(self, limit: int = 0) -> list[RawEquipment]:
        items = self._fetch_list()
        if limit:
            items = items[:limit]
        records: list[RawEquipment] = []
        for item in items:
            record = self._fetch_detail(item)
            records.append(record)
        return records

    def _fetch_list(self) -> list[EqnetListItem]:
        if not self.list_url:
            raise ValueError("EQNET_LIST_URL is required to fetch list items")
        response = self.session.get(self.list_url, timeout=self.timeout)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type or self.list_url.endswith(".json"):
            return self._parse_list_json(response.json())
        return self._parse_list_html(response.text)

    def _parse_list_json(self, payload) -> list[EqnetListItem]:
        items = payload
        if isinstance(payload, dict):
            items = payload.get("results") or payload.get("data") or payload.get("items") or []
        results: list[EqnetListItem] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            equipment_id = clean_text(
                str(
                    item.get("id")
                    or item.get("equipment_id")
                    or item.get("equipmentId")
                    or ""
                )
            )
            url = clean_text(str(item.get("url") or item.get("detail_url") or ""))
            name = clean_text(str(item.get("name") or item.get("equipment_name") or ""))
            org_name = clean_text(str(item.get("org_name") or item.get("organization") or ""))
            results.append(
                EqnetListItem(
                    equipment_id=equipment_id,
                    url=url,
                    name=name,
                    org_name=org_name,
                )
            )
        if not results and self.logger:
            self.logger.warning("No list items detected in eqnet JSON response")
        return results

    def _parse_list_html(self, html: str) -> list[EqnetListItem]:
        soup = BeautifulSoup(html, "html.parser")
        results: list[EqnetListItem] = []
        seen: set[str] = set()
        for link in soup.select("a[href]"):
            href = link.get("href")
            if not href:
                continue
            if not self._looks_like_detail_link(href):
                continue
            url = urljoin(self.list_url or "", href)
            if url in seen:
                continue
            seen.add(url)
            equipment_id = self._extract_id_from_url(url)
            name = clean_text(link.get_text(" ", strip=True))
            results.append(EqnetListItem(equipment_id=equipment_id, url=url, name=name, org_name=""))
        if not results and self.logger:
            self.logger.warning("No list items detected in eqnet HTML response")
        return results

    def _fetch_detail(self, item: EqnetListItem) -> RawEquipment:
        url = item.url or ""
        if not url and self.detail_url_template:
            url = self.detail_url_template.format(id=item.equipment_id)
        if not url:
            raise ValueError("Detail URL missing for item")
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        raw = self._parse_detail_html(response.text)
        raw.source_url = url
        if item.equipment_id:
            raw.equipment_id = item.equipment_id
        if item.name and not raw.name:
            raw.name = item.name
        if item.org_name and not raw.org_name:
            raw.org_name = item.org_name
        return raw

    def _parse_detail_html(self, html: str) -> RawEquipment:
        soup = BeautifulSoup(html, "html.parser")
        fields = self._extract_fields(soup)
        name = self._extract_name(soup, fields)

        raw = RawEquipment(
            name=name,
            category=self._pick_field(fields, ["カテゴリ", "分類"]),
            category_general=self._pick_field(fields, ["大分類", "カテゴリ大"]),
            category_detail=self._pick_field(fields, ["小分類", "カテゴリ小"]),
            org_name=self._pick_field(fields, ["所属", "機関", "組織"]),
            org_type=self._pick_field(fields, ["機関種別", "種別"]),
            address_raw=self._pick_field(fields, ["住所", "所在地"]),
            external_use=self._pick_field(fields, ["学外", "外部利用", "利用可否"]),
            fee_note=self._pick_field(fields, ["料金", "利用料", "費用"]),
            conditions_note=self._pick_field(fields, ["利用条件", "条件", "制限"]),
            source_updated_at=self._pick_field(fields, ["最終更新", "更新日"]),
        )
        return raw

    def _extract_fields(self, soup: BeautifulSoup) -> dict[str, str]:
        fields: dict[str, str] = {}
        for row in soup.select("table tr"):
            header = row.find("th")
            value = row.find("td")
            if not header or not value:
                continue
            label = normalize_label(header.get_text(" ", strip=True))
            content = clean_text(value.get_text(" ", strip=True))
            if label and content:
                fields[label] = content
        for dt in soup.select("dl dt"):
            dd = dt.find_next_sibling("dd")
            if not dd:
                continue
            label = normalize_label(dt.get_text(" ", strip=True))
            content = clean_text(dd.get_text(" ", strip=True))
            if label and content:
                fields[label] = content
        return fields

    def _extract_name(self, soup: BeautifulSoup, fields: dict[str, str]) -> str:
        name = (
            fields.get("機器名")
            or fields.get("設備名")
            or fields.get("装置名")
            or fields.get("名称")
        )
        if name:
            return name
        heading = soup.find(["h1", "h2"])
        if heading:
            return clean_text(heading.get_text(" ", strip=True))
        meta = soup.find("meta", attrs={"property": "og:title"})
        if meta and meta.get("content"):
            return clean_text(meta["content"])
        title = soup.title.string if soup.title else ""
        return clean_text(title)

    def _pick_field(self, fields: dict[str, str], keywords: Iterable[str]) -> str:
        for key, value in fields.items():
            for word in keywords:
                if word in key:
                    return value
        return ""

    def _looks_like_detail_link(self, href: str) -> bool:
        lowered = href.lower()
        return any(token in lowered for token in ["id=", "detail", "equipment", "eqnet"])

    def _extract_id_from_url(self, url: str) -> str:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        for key in ["id", "equipment_id", "equipmentId", "eqid", "eq_id"]:
            if key in params and params[key]:
                return params[key][0]
        path = parsed.path.rstrip("/").split("/")[-1]
        return path or ""
