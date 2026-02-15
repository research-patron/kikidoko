#!/usr/bin/env python3
"""Validate SEO blog article manifest."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

URL_PATTERN = re.compile(r"^/([a-z0-9-]+)/([a-z0-9-]+)/?$")
TOP_LINKS = {
    "/",
    "https://kikidoko.web.app/",
    "https://kikidoko.web.app",
}


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fp:
        return json.load(fp)


def parse_related_category(link: str) -> str | None:
    match = URL_PATTERN.match(link)
    if not match:
        return None
    return match.group(1)


def validate(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    policy = manifest.get("policy", {})
    required_fields = policy.get("required_fields", [])
    allowed_categories = set(policy.get("allowed_categories", []))
    articles = manifest.get("articles", [])
    quota = manifest.get("category_quota", {})

    if not isinstance(articles, list):
        return ["articles must be a list."]

    if len(articles) != 20:
        errors.append(f"article count must be 20, got {len(articles)}.")

    category_counter: Counter[str] = Counter()
    keyword_counter: Counter[str] = Counter()
    seen_ids: set[str] = set()

    for article in articles:
        aid = article.get("id", "<missing-id>")
        if aid in seen_ids:
            errors.append(f"[{aid}] duplicated id.")
        seen_ids.add(aid)

        for key in required_fields:
            if key not in article:
                errors.append(f"[{aid}] missing required field: {key}.")

        category = article.get("category")
        if category not in allowed_categories:
            errors.append(f"[{aid}] invalid category: {category}.")
        else:
            category_counter[category] += 1

        url = article.get("url", "")
        match = URL_PATTERN.match(url)
        if not match:
            errors.append(f"[{aid}] invalid url format: {url}.")
        else:
            url_category = match.group(1)
            if category != url_category:
                errors.append(
                    f"[{aid}] category/url mismatch: category={category}, url={url}."
                )

        primary_keyword = article.get("primary_keyword", "")
        if not isinstance(primary_keyword, str) or not primary_keyword.strip():
            errors.append(f"[{aid}] primary_keyword is empty.")
        else:
            keyword_counter[primary_keyword.strip()] += 1

        title = article.get("title", "")
        if not isinstance(title, str) or not title.strip():
            errors.append(f"[{aid}] title is empty.")
        else:
            primary_head = primary_keyword.split(" ")[0].split("/")[0] if primary_keyword else ""
            if primary_head and primary_head not in title[:12]:
                errors.append(
                    f"[{aid}] title should place primary keyword near the beginning."
                )

        target_chars = article.get("target_chars", {})
        if not isinstance(target_chars, dict):
            errors.append(f"[{aid}] target_chars must be an object.")
        else:
            min_chars = target_chars.get("min")
            max_chars = target_chars.get("max")
            if not isinstance(min_chars, int) or not isinstance(max_chars, int):
                errors.append(f"[{aid}] target_chars min/max must be integers.")
            elif min_chars <= 0 or max_chars <= 0 or min_chars >= max_chars:
                errors.append(
                    f"[{aid}] invalid target_chars range: min={min_chars}, max={max_chars}."
                )

        secondary_keywords = article.get("secondary_keywords", [])
        if not isinstance(secondary_keywords, list) or len(secondary_keywords) == 0:
            errors.append(f"[{aid}] secondary_keywords must be a non-empty list.")

        related_links = article.get("related_links", [])
        if not isinstance(related_links, list):
            errors.append(f"[{aid}] related_links must be a list.")
            continue
        if len(related_links) < 4:
            errors.append(f"[{aid}] related_links must include at least 4 links.")

        has_top_link = any(link in TOP_LINKS for link in related_links)
        if not has_top_link:
            errors.append(f"[{aid}] missing app top link in related_links.")

        related_categories = [parse_related_category(link) for link in related_links]
        same_category_count = sum(1 for cat in related_categories if cat == category)
        other_category_count = sum(
            1 for cat in related_categories if cat and cat != category
        )
        if same_category_count < 2:
            errors.append(
                f"[{aid}] requires at least 2 same-category related links."
            )
        if other_category_count < 1:
            errors.append(
                f"[{aid}] requires at least 1 cross-category related link."
            )

        cta_url = article.get("cta_url", "")
        if cta_url not in TOP_LINKS:
            errors.append(f"[{aid}] cta_url must point to app top.")

    duplicated_keywords = [k for k, count in keyword_counter.items() if count > 1]
    if duplicated_keywords:
        errors.append(f"duplicated primary keywords: {duplicated_keywords}")

    for category, expected in quota.items():
        actual = category_counter.get(category, 0)
        if actual != expected:
            errors.append(
                f"category quota mismatch: {category} expected={expected} actual={actual}."
            )

    schedule = manifest.get("publishing_schedule", {})
    month_1_ids = schedule.get("month_1_ids", [])
    month_2_ids = schedule.get("month_2_ids", [])
    if len(month_1_ids) != 12:
        errors.append(f"month_1_ids must be 12, got {len(month_1_ids)}.")
    if len(month_2_ids) != 8:
        errors.append(f"month_2_ids must be 8, got {len(month_2_ids)}.")
    if set(month_1_ids) & set(month_2_ids):
        errors.append("month_1_ids and month_2_ids must be disjoint.")
    if set(month_1_ids + month_2_ids) != seen_ids:
        errors.append("publishing schedule ids must exactly cover all article ids.")

    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python3 tools/validate_blog_articles.py <path/to/articles.json>")
        return 2

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"file not found: {path}")
        return 2

    try:
        manifest = load_manifest(path)
    except json.JSONDecodeError as exc:
        print(f"json decode error: {exc}")
        return 2

    errors = validate(manifest)
    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    articles = manifest.get("articles", [])
    category_counter = Counter(a["category"] for a in articles)
    print("Validation passed.")
    print(f"- article_count: {len(articles)}")
    print(f"- category_counts: {dict(category_counter)}")
    print("- schedule: month_1=12 month_2=8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
