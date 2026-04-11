# Agent Entry Point

このファイルは起動時チェックリストです。作業開始前に必ず確認してください。

## Startup Checklist (Mandatory)
1. 最初に `/Users/niigatadaigakukenkyuuyou/Desktop/開発アプリ/kikidoko/AGENTS.md` を開き、最新ルールを確認する。
2. 検証フェーズでは Python/Node 等のスクリプト確認処理を使わない。
3. 検証は Codex 手作業で行い、live は CLI で公開 JSON を確認する。
4. 検証でスクリプトを使った場合、その検証は無効。手作業で再検証する。
5. `firebase deploy` の前に、必ず `frontend/update-notes/entries/YYYY/` の update note を追加または更新し、manifest 生成と predeploy guard と public tree audit を通す。

## Required Report Items (Mandatory)
- `検証フェーズでのスクリプト使用: 0回`
- 確認した公開URLと確認時刻
- 手作業確認の判定結果（PASS/FAIL）
