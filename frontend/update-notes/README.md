# Update Notes

`frontend/update-notes/entries/YYYY/` 配下の Markdown が、アップデート情報ページの source-of-truth です。

## ルール

- GitHub 反映前に、必ず最新の更新内容を 1 件追加または更新する
- ファイル名は `YYYY-MM-DD-slug.md`
- frontmatter は次を必須とする
  - `title`
  - `published_at`
  - `summary`
  - `version_label`
  - `status`
  - `tags`
- `published_at` は JST の ISO 8601 形式を使う
  - 例: `2026-03-28T18:00:00+09:00`

## 生成フロー

1. `python3 tools/build_blog_articles_manifest.py`
2. `python3 tools/build_update_info_manifest.py`
3. `python3 tools/verify_update_info_predeploy.py`
4. `python3 tools/audit_public_tree.py`
5. GitHub 更新により Cloudflare Pages へ反映する

## 公開文面の基本方針

- 利用者に見える変更だけを書く
- 内部の契約名、スクリプト名、ファイルパス、配信基盤名、監査名は書かない
- `manual_content_v1` のような内部名は「初心者向け機器ガイド」など、利用者が分かる表現に置き換える
- tags は日本語の利用者向け分類にし、snake_case やファイル名を入れない

## 公開生成物

- source: `frontend/update-notes/entries/YYYY/`
- manifest: `frontend/dist/update-info/index.json`
