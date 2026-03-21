# Manual Verification Log

- サイクルID: CYCLE-REBUILD-0003
- バッチID: BATCH-20260306-CYCLE0003-10
- 検証者: codex-manual
- 検証日: 2026-03-07 JST

## Deployment Status
- 本番URL (web.app): https://kikidoko.web.app
- 本番URL (firebaseapp.com): https://kikidoko.firebaseapp.com
- 参照バージョン文字列: `20260306-bootstrap-sync-1`
- 配信確認時刻: 2026-03-07 08:36 JST 前後

## Target Equipments
- `VRY5cXiT090GLPf9fhAt`
  - 機器名: 化学発光イメージング装置 －型式： LuminoGraph EMⅠ
  - 確認URL: https://kikidoko.web.app/data/equipment_detail_shards/detail-12.json?v=20260306-bootstrap-sync-1
- `ZpEsD1VJ5uJdSfwLOx3z`
  - 機器名: 粒子径・分子量測定装置－型式：ZETASIZER Nano-S
  - 確認URL: https://kikidoko.web.app/data/equipment_detail_shards/detail-2c.json?v=20260306-bootstrap-sync-1
- `acudKLs6rShQtvQwF6tA`
  - 機器名: 紫外可視分光光度計－型式： BioSpectrometer kinetic
  - 確認URL: https://kikidoko.web.app/data/equipment_detail_shards/detail-1b.json?v=20260306-bootstrap-sync-1
- `WA5NfqWUHxVa97Pgyojx`
  - 機器名: 蛍光分光光度計(FL)－型式：F-2500
  - 確認URL: https://kikidoko.web.app/data/equipment_detail_shards/detail-25.json?v=20260306-bootstrap-sync-1
- `mvHeWRPnzgxqa2wHKaqo`
  - 機器名: 3Dプリンタ
  - 確認URL: https://kikidoko.web.app/data/equipment_detail_shards/detail-3d.json?v=20260306-bootstrap-sync-1
- `TOKUSHIMA-6`
  - 機器名: 3Dプリンタ
  - 確認URL: https://kikidoko.web.app/data/equipment_detail_shards/detail-3d.json?v=20260306-bootstrap-sync-1
- `TOKUSHIMA-72`
  - 機器名: 光造形3Dプリンタ
  - 確認URL: https://kikidoko.web.app/data/equipment_detail_shards/detail-1d.json?v=20260306-bootstrap-sync-1
- `vLxG7JK9l1a27ArfGbY1`
  - 機器名: 全自動タンパク質合成システム－型式：GenDecorder
  - 確認URL: https://kikidoko.web.app/data/equipment_detail_shards/detail-13.json?v=20260306-bootstrap-sync-1
- `GsgCedK7rtQUoIzvlFnK`
  - 機器名: 卓上タンパク質合成システム－型式：Protemist DT
  - 確認URL: https://kikidoko.web.app/data/equipment_detail_shards/detail-1b.json?v=20260306-bootstrap-sync-1
- `YgBfgj2Glg50OMudGFzi`
  - 機器名: 全自動タンパク質合成システム－型式：GenDecorder
  - 確認URL: https://kikidoko.web.app/data/equipment_detail_shards/detail-29.json?v=20260306-bootstrap-sync-1

## Manual Verification Result
- 10件すべてで live detail shard 上の `manual_content_v1.review.status=approved` を確認
- 10件すべてで `beginner_guide.principle_ja` と `sample_guidance_ja` が存在し、装置名を含む本文であることを確認
- 3Dプリンタ2件は同一機種説明の使い回しであり、ユーザー方針の「同種は使い回し可」に整合
- 全自動タンパク質合成システム2件も同一機種説明の使い回しであり、装置不一致は確認されなかった
- 本検証は live JSON を目視読取りして実施し、対象記事が本番配信物に載っていることを確認した

## Verification Integrity
- 検証中スクリプト使用回数（Python/Node）: 0
- 使用した確認手段: `curl` による live 配信物取得、`jq` による対象行抽出、目視判定

## Final Decision
- 判定: PASS
- 次アクション: `manual_guard close` 実行後、CYCLE-REBUILD-0004 の preflight を開始
