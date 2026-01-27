from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class CrawlerSettings:
    project_id: str
    credentials_path: str | None
    dry_run: bool
    log_level: str
    request_timeout: int
    output_path: str | None
    geocode_enabled: bool
    geocode_min_interval: float


def load_settings() -> CrawlerSettings:
    project_id = os.getenv("KIKIDOKO_PROJECT_ID", "")
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    dry_run = os.getenv("KIKIDOKO_DRY_RUN", "0") in {"1", "true", "True"}
    log_level = os.getenv("KIKIDOKO_LOG_LEVEL", "INFO")
    request_timeout = int(os.getenv("KIKIDOKO_REQUEST_TIMEOUT", "20"))
    output_path = os.getenv("KIKIDOKO_OUTPUT_PATH")
    geocode_enabled = os.getenv("KIKIDOKO_GEOCODE", "1") in {"1", "true", "True"}
    geocode_min_interval = float(os.getenv("KIKIDOKO_GEOCODE_MIN_INTERVAL", "0.25"))
    return CrawlerSettings(
        project_id=project_id,
        credentials_path=credentials_path,
        dry_run=dry_run,
        log_level=log_level,
        request_timeout=request_timeout,
        output_path=output_path,
        geocode_enabled=geocode_enabled,
        geocode_min_interval=geocode_min_interval,
    )
