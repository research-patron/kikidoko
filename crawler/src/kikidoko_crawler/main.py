from __future__ import annotations

import argparse
import logging

from .config import load_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kikidoko crawler")
    parser.add_argument(
        "--source",
        required=True,
        choices=["eqnet", "university", "csv"],
        help="Data source to crawl",
    )
    parser.add_argument("--dry-run", action="store_true", help="Skip Firestore writes")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of items to process (0 = no limit)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = load_settings()
    dry_run = settings.dry_run or args.dry_run

    logging.basicConfig(level=settings.log_level, format="%(levelname)s: %(message)s")
    logger = logging.getLogger(__name__)

    if not dry_run and not settings.project_id:
        raise SystemExit("KIKIDOKO_PROJECT_ID is required when not running dry")

    logger.info(
        "Starting crawl: source=%s dry_run=%s limit=%s",
        args.source,
        dry_run,
        args.limit or "none",
    )
    logger.warning("Crawler implementation is pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
