---
title: 公開ファイル構成と配信設定を整理
published_at: 2026-03-28T20:30:00+09:00
summary: 公開ツリーの不要ファイルを整理し、配信設定と更新ルールを見直しました。
version_label: 2026.03.28
status: published
tags:
  - 配信最適化
  - 運用整理
  - ブログ
---

## 主な更新

- 公開用の patch ファイルを `patches/site-ui-overrides.*` に整理し、古い命名の patch を削除しました。
- 公開不要だったブログ原稿や運用メモを公開外へ移し、公開側は `blog/articles.json` だけを使う構成に変更しました。
- Firebase Hosting の cache-control と predeploy 監査を見直し、不要ファイルが公開ツリーに混ざらないようにしました。
