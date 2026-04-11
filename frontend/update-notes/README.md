# Update Notes

`frontend/update-notes/entries/YYYY/` 配下の Markdown が、アップデート情報ページの source-of-truth です。

## ルール

- Firebase Hosting 前に、必ず最新の更新内容を 1 件追加または更新する
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
1. `python3 tools/build_update_info_manifest.py`
2. `python3 tools/verify_update_info_predeploy.py`
3. `python3 tools/audit_public_tree.py`
4. `firebase deploy --only hosting,firestore:rules --project kikidoko`

## 公開生成物

- source: `frontend/update-notes/entries/YYYY/`
- manifest: `frontend/dist/update-info/index.json`
