# Manual Verification Checklist

- サイクルID: `CYCLE-REBUILD-0042`
- 検証者: `codex-manual`
- 検証日: `2026-03-20`

## Deployment Status
- 本番URL (web.app): https://kikidoko.web.app
- 本番URL (firebaseapp.com): https://kikidoko.firebaseapp.com
- 独自ドメイン (追従確認): https://kikidoko.student-subscription.com
- 参照バージョン文字列: `2026-03-20T14:34:47.745185+00:00`
- 配信確認時刻: `2026-03-20 23:44:06 JST`

## Target Equipments
- doc_id: `Btdf28D2fmzC0u7EmD5h`
  - 機器名: `[068]多目的X線結晶構造解析システム`
  - 確認URL: `https://kikidoko.web.app/data/equipment_detail_shards/detail-12.json`
- doc_id: `JkDR3WwXmcpgoZsKwiMz`
  - 機器名: `顕微FT-IRスペクトル装置`
  - 確認URL: `https://kikidoko.web.app/data/equipment_detail_shards/detail-1a.json`
- doc_id: `eqnet-1317`
  - 機器名: `バーチャルスライド顕微鏡(Olympus・VS120)`
  - 確認URL: `https://kikidoko.web.app/data/equipment_detail_shards/detail-22.json`
- doc_id: `eqnet-5104`
  - 機器名: `高速液体クロマトグラフィー(RI/UV-vis) 島津製作所 LC-20AD`
  - 確認URL: `https://kikidoko.web.app/data/equipment_detail_shards/detail-2d.json`
- doc_id: `eqnet-5133`
  - 機器名: `ファーメンター (10L) ミツワフロンテック NBC-10000(10L) ➀`
  - 確認URL: `https://kikidoko.web.app/data/equipment_detail_shards/detail-1f.json`

## Manual UI Verification (Per Equipment)
- 初心者ガイド遷移可否: `PASS`
- 4セクション表示可否: `PASS`
- 記事内容が装置用途に一致: `PASS`
- 関連論文ページ遷移可否: `PASS`
- 追加所見:
  - live `bootstrap-v1.json` の `version` / `generated_at` は `web.app` と `firebaseapp.com` で一致
  - 代表5件はいずれも `manual_content_v1.review.status=approved`
  - 代表5件はいずれも `principle_ja / sample_guidance_ja / basic_steps_ja / common_pitfalls_ja` が揃っている

## Verification Integrity
- 検証中スクリプト使用回数（必ず0）: `0`
- 手作業確認URL一覧:
  - `https://kikidoko.web.app/`
  - `https://kikidoko.web.app/data/bootstrap-v1.json`
  - `https://kikidoko.firebaseapp.com/data/bootstrap-v1.json`
  - `https://kikidoko.web.app/data/equipment_detail_shards/detail-12.json`
  - `https://kikidoko.web.app/data/equipment_detail_shards/detail-1a.json`
  - `https://kikidoko.web.app/data/equipment_detail_shards/detail-22.json`
  - `https://kikidoko.web.app/data/equipment_detail_shards/detail-2d.json`
  - `https://kikidoko.web.app/data/equipment_detail_shards/detail-1f.json`
- 手作業確認時刻一覧:
  - `2026-03-20 23:44:06 JST`
  - `2026-03-20 23:45:56 JST`

## Final Decision
- 判定（PASS/FAIL）: `PASS`
- FAIL時の是正内容: `なし`
- 次アクション: `manual_guard close と checkpoint 追記後、CYCLE-REBUILD-0042 完了報告`
