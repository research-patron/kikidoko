# blog content plan

This directory stores the SEO article planning assets for pre-release publishing.

## Files

- `seo-article-report-2026-02.md`: finalized report for SEO article strategy.
- `articles.json`: canonical metadata for 20 planned articles.

## URL policy

All article URLs must follow:

`/blog/{category}/{slug}`

Allowed categories:

- `guide`
- `equipment`
- `region`
- `workflow`

## Validation

Run from repository root:

```sh
python3 tools/validate_blog_articles.py frontend/public/blog/articles.json
```

This checks:

- required fields
- category quotas (4/8/5/3)
- URL format and category alignment
- unique primary keywords
- target character ranges
- minimum internal links and app-top CTA link

Additional checks:

- leading `#` title line handling
- markdown token leftovers after conversion
- block-editor-compatible output basis

## Per-article preflight

```sh
python3 tools/seo_preflight_article.py \
  --article-id guide-01 \
  --manifest frontend/public/blog/articles.json \
  --draft frontend/public/blog/drafts/guide-01.md \
  --report-out /tmp/guide-01-seo-report.json
```

## Publish to WordPress

```sh
WP_USER='<wp username>' \
WP_APP_PASSWORD='<wp application password>' \
python3 tools/wp_publish_article.py \
  --article-id guide-01 \
  --manifest frontend/public/blog/articles.json \
  --wp-base https://kikidoko.student-subscription.com/blog \
  --draft frontend/public/blog/drafts/guide-01.md \
  --ensure-all-categories
```

If your environment cannot validate TLS certificates, add `--insecure`.

## Content rules

- Do not include the post title as a markdown H1 in the draft body.
- Use markdown headings from `##` onward for body sections.
- The publisher writes Gutenberg blocks (`wp:paragraph`, `wp:heading`, `wp:list`) to WordPress.
- Inline markdown (`**bold**`, `*italic*`, `` `code` ``, `[link](url)`) is converted to HTML before publish.
