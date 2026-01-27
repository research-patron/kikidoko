from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

from .models import EquipmentRecord

GSI_GEOCODE_URL = "https://msearch.gsi.go.jp/address-search/AddressSearch"
SKIP_ADDRESS = {"", "不明", "所在地不明"}


@dataclass
class GeocodeSettings:
    timeout: int
    min_interval: float = 0.25


class GsiGeocoder:
    def __init__(self, settings: GeocodeSettings) -> None:
        self._settings = settings
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "kikidoko-crawler/0.1"})
        self._last_request = 0.0
        self._cache: dict[str, tuple[float, float] | None] = {}

    def geocode(self, query: str) -> tuple[float, float] | None:
        cleaned = query.strip()
        if not cleaned:
            return None
        if cleaned in self._cache:
            return self._cache[cleaned]
        self._throttle()
        response = self._session.get(
            GSI_GEOCODE_URL,
            params={"q": cleaned},
            timeout=self._settings.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload:
            self._cache[cleaned] = None
            return None
        coords = payload[0].get("geometry", {}).get("coordinates")
        if not coords or len(coords) < 2:
            self._cache[cleaned] = None
            return None
        lng, lat = coords[0], coords[1]
        result = (float(lat), float(lng))
        self._cache[cleaned] = result
        return result

    def _throttle(self) -> None:
        if self._settings.min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._settings.min_interval:
            time.sleep(self._settings.min_interval - elapsed)
        self._last_request = time.monotonic()


def build_geocode_query(record: EquipmentRecord) -> str:
    address = (record.address_raw or "").strip()
    if address in SKIP_ADDRESS:
        address = ""
    if address:
        return address
    org_name = (record.org_name or "").strip()
    if not org_name:
        return ""
    if record.prefecture and record.prefecture not in org_name:
        return f"{record.prefecture} {org_name}"
    return org_name


def enrich_with_geocode(
    records: list[EquipmentRecord],
    settings: GeocodeSettings,
    logger: logging.Logger | None = None,
) -> None:
    active_logger = logger or logging.getLogger(__name__)
    geocoder = GsiGeocoder(settings)
    for record in records:
        if record.lat is not None and record.lng is not None:
            continue
        query = build_geocode_query(record)
        if not query:
            continue
        try:
            result = geocoder.geocode(query)
        except requests.RequestException as exc:
            active_logger.warning("Geocode failed for %s: %s", query, exc)
            continue
        if result:
            record.lat, record.lng = result
        else:
            active_logger.debug("Geocode returned no result: %s", query)
