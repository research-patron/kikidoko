#!/usr/bin/env python3
"""SEO preflight checks for a single blog draft."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from blog_content_utils import (
    count_seo_chars,
    detect_markdown_tokens,
    extract_markdown_links,
    markdown_to_blocks,
    strip_leading_h1_if_title_match,
)

URL_PATTERN = re.compile(r"^/([a-z0-9-]+)/([a-z0-9-]+)/?$")
APP_SITE_ROOT = "https://kikidoko.web.app"
BLOG_HOSTS = {
    "kikidoko-blog.student-subscription.com",
}
APP_TOP_LINKS = {
    "/",
    APP_SITE_ROOT,
    f"{APP_SITE_ROOT}/",
}


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fp:
        return json.load(fp)


def find_article(manifest: dict[str, Any], article_id: str) -> dict[str, Any]:
    articles = manifest.get("articles", [])
    for article in articles:
        if article.get("id") == article_id:
            return article
    raise KeyError(f"article id not found: {article_id}")


def normalize_blog_path(path: str) -> str | None:
    path = path.strip()
    if not path:
        return None
    if path.startswith("/blog/"):
        path = path[len("/blog") :]
    if path == "/":
        return "/"
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{path.rstrip('/')}/"


def normalize_link_to_path(link: str) -> str | None:
    link = link.strip()
    if not link:
        return None
    if link.startswith("/"):
        return normalize_blog_path(link)
    parsed = urlparse(link)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        if parsed.netloc not in BLOG_HOSTS:
            return None
        return normalize_blog_path(parsed.path or "/")
    return None


def is_app_top_link(link: str) -> bool:
    link = link.strip()
    if link in APP_TOP_LINKS:
        return True
    parsed = urlparse(link)
    if parsed.scheme in {"http", "https"} and parsed.netloc == "kikidoko.web.app":
        normalized = (parsed.path or "/").rstrip("/")
        return normalized == ""
    return False


def category_from_link(link: str) -> str | None:
    path = normalize_link_to_path(link)
    if not path:
        return None
    match = URL_PATTERN.match(path)
    if not match:
        return None
    return match.group(1)


def validate_title_head(title: str, primary_keyword: str) -> bool:
    primary_head = primary_keyword.split("/")[0].strip().split(" ")[0]
    if not primary_head:
        return False
    return primary_head in title[:14]


def run_preflight(article: dict[str, Any], draft_text: str) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {}

    category = article.get("category", "")
    slug = article.get("slug", "")
    target_chars = article.get("target_chars", {})
    min_chars = target_chars.get("min")
    max_chars = target_chars.get("max")
    title = article.get("title", "")
    primary_keyword = article.get("primary_keyword", "")
    url = article.get("url", "")

    if not validate_title_head(title, primary_keyword):
        errors.append("title does not include primary keyword head near the beginning.")
    checks["title_head_ok"] = len(errors) == 0

    h1_info = strip_leading_h1_if_title_match(draft_text, title=title)
    sanitized_draft = h1_info["text"]
    leading_h1_detected = bool(h1_info["leading_h1_detected"])
    body_title_duplication = bool(h1_info["body_title_duplication"])
    checks["leading_h1_detected"] = leading_h1_detected
    checks["body_title_duplication"] = body_title_duplication
    if leading_h1_detected and not body_title_duplication:
        errors.append("leading H1 exists but does not match title; remove it before publish.")
    elif leading_h1_detected and body_title_duplication:
        warnings.append("leading H1 duplicate title detected; it will be auto-stripped on publish.")

    char_count = count_seo_chars(sanitized_draft)
    checks["char_count"] = char_count
    checks["target_chars"] = {"min": min_chars, "max": max_chars}
    if not isinstance(min_chars, int) or not isinstance(max_chars, int):
        errors.append("target_chars min/max are missing or invalid.")
    elif char_count < min_chars or char_count > max_chars:
        errors.append(f"char count out of range: {char_count} (target {min_chars}-{max_chars}).")

    links = extract_markdown_links(sanitized_draft)
    checks["total_markdown_links"] = len(links)
    if len(links) < 4:
        errors.append(f"internal link requirement failed: only {len(links)} markdown links found.")

    if not any(is_app_top_link(link) for link in links):
        errors.append("missing app top link.")

    same_category_count = 0
    cross_category_count = 0
    for link in links:
        linked_category = category_from_link(link)
        if linked_category is None:
            continue
        if linked_category == category:
            same_category_count += 1
        elif linked_category != category:
            cross_category_count += 1
    checks["same_category_links"] = same_category_count
    checks["cross_category_links"] = cross_category_count
    if same_category_count < 2:
        errors.append(
            f"same-category link requirement failed: {same_category_count} found (need >=2)."
        )
    if cross_category_count < 1:
        errors.append(
            f"cross-category link requirement failed: {cross_category_count} found (need >=1)."
        )

    expected_path = f"/{category}/{slug}/"
    checks["expected_path"] = expected_path
    if not URL_PATTERN.match(url or ""):
        errors.append(f"manifest article url is invalid: {url}")
    elif url != expected_path:
        errors.append(f"manifest article url mismatch: {url} != {expected_path}")

    block_content = markdown_to_blocks(sanitized_draft)
    markdown_tokens_left = detect_markdown_tokens(block_content)
    checks["markdown_tokens_left"] = markdown_tokens_left
    if markdown_tokens_left:
        errors.append(f"unconverted markdown tokens remain after block conversion: {markdown_tokens_left}")

    has_h1_in_blocks = bool(re.search(r"<h1\b", block_content, flags=re.IGNORECASE))
    checks["has_h1_in_blocks"] = has_h1_in_blocks
    if has_h1_in_blocks:
        errors.append("converted block content includes h1 tag.")

    primary_head = primary_keyword.split("/")[0].strip().split(" ")[0]
    if primary_head and primary_head not in sanitized_draft:
        warnings.append("primary keyword head not found in body text.")

    return {
        "article_id": article.get("id"),
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SEO preflight for one article draft.")
    parser.add_argument("--article-id", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--draft", required=True)
    parser.add_argument("--report-out")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest)
    draft_path = Path(args.draft)

    if not manifest_path.exists():
        print(f"manifest not found: {manifest_path}")
        return 2
    if not draft_path.exists():
        print(f"draft not found: {draft_path}")
        return 2

    try:
        manifest = load_manifest(manifest_path)
        article = find_article(manifest, args.article_id)
        draft_text = draft_path.read_text(encoding="utf-8")
        report = run_preflight(article, draft_text)
    except Exception as exc:  # noqa: BLE001
        print(f"preflight error: {exc}")
        return 2

    if args.report_out:
        Path(args.report_out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
