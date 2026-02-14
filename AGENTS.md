# AGENTS

このリポジトリで Frontend / Firebase Hosting を更新するエージェント向けの必須ルールです。

## 必須ルール

1. `frontend` または `firebase.json` を変更する作業では、開始前に必ず `/Users/niigatadaigakukenkyuuyou/Downloads/kikidoko/docs/runbooks/firebase-hosting-update.md` を読むこと。
2. 作業ログまたは最終報告に `runbook参照済み` を明記すること。
3. `frontend/public/equipment_snapshot.json.gz` は毎回デプロイ前に再生成し、Git にはコミットしないこと。
4. `/blog/*` リダイレクト設定を壊さないこと（`kikidoko-blog.student-subscription.com` へ 301）。
5. 本番デプロイ前に preview チャネルで検証し、`/equipment_snapshot.json.gz` が `200` かつ HTML ではないことを確認すること。

## 参照先

- 運用手順: `/Users/niigatadaigakukenkyuuyou/Downloads/kikidoko/docs/runbooks/firebase-hosting-update.md`
