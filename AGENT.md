# Agent Entry Point

このファイルは起動時チェックリストです。作業開始前に必ず確認してください。

## Startup Checklist (Mandatory)
1. 最初に `/Users/niigatadaigakukenkyuuyou/Desktop/開発アプリ/kikidoko/AGENTS.md` を開き、最新ルールを確認する。
2. 検証フェーズでは Python/Node 等のスクリプト確認処理を使わない。
3. 検証は Codex 手作業で行い、live は CLI で公開 JSON を確認する。
4. 検証でスクリプトを使った場合、その検証は無効。手作業で再検証する。
5. 静的公開物の反映は `firebase deploy` ではなく GitHub 更新で行う。原則は `branch -> Cloudflare Pages preview 確認 -> PR -> main 反映 -> Cloudflare Pages 本番` とする。
6. preview 確認の正規URLは、Cloudflare Pages の deployment details または API が返す branch alias を真実源として扱うこと。`https://<sanitized-branch>.kikidoko.pages.dev` を手元で機械的に組み立てて確定扱いしてはならない。
7. preview 対象ブランチは `develop`, `feat/*`, `fix/*`, `chore/*`, `docs/*` とし、`dependabot/*` は preview 自動配信対象から除外する前提で扱う。
8. ユーザーが明示的に「main に反映」と指示した場合のみ、PR を省略または main 反映まで進めてよい。
9. Firebase 側で更新してよいのは Firestore データのみとし、Firebase Hosting 操作はユーザーの明示指示がない限り行わない。
10. GitHub 反映前に、必ず `frontend/update-notes/entries/YYYY/` の update note を追加または更新し、manifest 生成と predeploy guard と public tree audit を通す。
11. ファイルやコードを変更した作業の完了時には、`main` にプッシュして一般公開するか、開発プレビューへ反映するかを必ずユーザーに確認すること。
12. 開発プレビューへ反映する場合は、Cloudflare Pages の deployment details または API で確認した branch alias の確認URLを必ず提示すること。Cloudflare Access の login への 302/200 のみでは確認完了扱いにしない。

## Required Report Items (Mandatory)
- `検証フェーズでのスクリプト使用: 0回`
- 確認した公開URLと確認時刻
- 手作業確認の判定結果（PASS/FAIL）
