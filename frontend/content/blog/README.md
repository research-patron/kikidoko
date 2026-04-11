# Blog Content Source

このディレクトリはブログ記事の source-of-truth です。公開配信に必要な生成物は別途 `frontend/dist` に出力し、source markdown や運用メモは公開しません。

## Layout

- `articles.json`: 記事メタデータの source manifest
- `articles/*.md`: 記事本文の source markdown
- `plans/*.md`: 公開不要の planning note
- `ops/*.md|*.json`: 公開不要の運用メモ

## URL policy

All article URLs must follow:

`/{category}/{slug}/`

Allowed categories:

- `guide`
- `equipment`
- `region`
- `workflow`

## Validation

Run from repository root:

```sh
python3 tools/validate_blog_articles.py frontend/content/blog/articles.json
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
  --manifest frontend/content/blog/articles.json \
  --draft frontend/content/blog/articles/guide-01.md \
  --report-out /tmp/guide-01-seo-report.json
```

## Publish to WordPress

```sh
WP_USER='<wp username>' \
WP_APP_PASSWORD='<wp application password>' \
python3 tools/wp_publish_article.py \
  --article-id guide-01 \
  --manifest frontend/content/blog/articles.json \
  --wp-base https://kikidoko-blog.student-subscription.com \
  --draft frontend/content/blog/articles/guide-01.md \
  --ensure-all-categories
```

If your environment cannot validate TLS certificates, add `--insecure`.

## Content rules

- Do not include the post title as a markdown H1 in the draft body.
- Use markdown headings from `##` onward for body sections.
- The publisher writes Gutenberg blocks (`wp:paragraph`, `wp:heading`, `wp:list`) to WordPress.
- Inline markdown (`**bold**`, `*italic*`, `` `code` ``, `[link](url)`) is converted to HTML before publish.
- App CTA URL must point to `https://kikidoko.web.app/`.

## Public Output

公開側で参照するのは `frontend/dist/blog/articles.json` だけです。生成は次で行います。

```sh
python3 tools/build_blog_articles_manifest.py
```
