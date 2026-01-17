from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class CrawlerSettings:
    project_id: str
    credentials_path: str | None
    dry_run: bool
    log_level: str
    eqnet_list_url: str | None
    eqnet_detail_url_template: str | None
    request_timeout: int
    output_path: str | None


def load_settings() -> CrawlerSettings:
    project_id = os.getenv("KIKIDOKO_PROJECT_ID", "")
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    dry_run = os.getenv("KIKIDOKO_DRY_RUN", "0") in {"1", "true", "True"}
    log_level = os.getenv("KIKIDOKO_LOG_LEVEL", "INFO")
    eqnet_list_url = os.getenv("EQNET_LIST_URL")
    eqnet_detail_url_template = os.getenv("EQNET_DETAIL_URL_TEMPLATE")
    request_timeout = int(os.getenv("KIKIDOKO_REQUEST_TIMEOUT", "20"))
    output_path = os.getenv("KIKIDOKO_OUTPUT_PATH")
    return CrawlerSettings(
        project_id=project_id,
        credentials_path=credentials_path,
        dry_run=dry_run,
        log_level=log_level,
        eqnet_list_url=eqnet_list_url,
        eqnet_detail_url_template=eqnet_detail_url_template,
        request_timeout=request_timeout,
        output_path=output_path,
    )
