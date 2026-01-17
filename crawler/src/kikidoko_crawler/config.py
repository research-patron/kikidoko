from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class CrawlerSettings:
    project_id: str
    credentials_path: str | None
    dry_run: bool
    log_level: str


def load_settings() -> CrawlerSettings:
    project_id = os.getenv("KIKIDOKO_PROJECT_ID", "")
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    dry_run = os.getenv("KIKIDOKO_DRY_RUN", "0") in {"1", "true", "True"}
    log_level = os.getenv("KIKIDOKO_LOG_LEVEL", "INFO")
    return CrawlerSettings(
        project_id=project_id,
        credentials_path=credentials_path,
        dry_run=dry_run,
        log_level=log_level,
    )
