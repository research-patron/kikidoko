# Manual Verification Checklist Template (No Script)

- サイクルID: CYCLE-REBUILD-0043
- 検証者: Codex
- 検証日: 2026-03-21

## Deployment Status
- 本番URL (web.app): https://kikidoko.web.app
- 本番URL (firebaseapp.com): https://kikidoko.firebaseapp.com
- 独自ドメイン (追従確認): 未確認
- 参照バージョン文字列: 2026-03-21T00:29:24.121982+00:00
- 配信確認時刻: 2026-03-21 09:34:57 JST - 2026-03-21 09:39:30 JST

## Target Equipments
- doc_id: 2tQSyysW5GzUbZBLqC9k
  - 機器名: 超低温フリーザー_03 パナソニックヘルスケア MDF-DC500-VX-PJ
  - 確認URL: https://kikidoko.web.app/#/beginner/2tQSyysW5GzUbZBLqC9k
- doc_id: YOyGKvBvvqYAzXGWjO8R
  - 機器名: 旭町ラボ オープンラボスペース 202実験室(C)-1
  - 確認URL: https://kikidoko.web.app/#/beginner/YOyGKvBvvqYAzXGWjO8R
- doc_id: d1chcYWvdrO4bm83FPKp
  - 機器名: マイクロロガー
  - 確認URL: https://kikidoko.web.app/#/beginner/d1chcYWvdrO4bm83FPKp
- doc_id: jbyanFAconRcEQs5BUum
  - 機器名: 旭町ラボ オープンラボスペース 202実験室(C)-2
  - 確認URL: https://kikidoko.web.app/data/equipment_detail_shards/detail-21.json
- doc_id: oaUTVMdanLnLc1uUt27D
  - 機器名: マルチスペクトラルカメラ
  - 確認URL: https://kikidoko.web.app/data/equipment_detail_shards/detail-23.json

## Manual UI Verification (Per Equipment)
- 初心者ガイド遷移可否: PASS
- 4セクション表示可否: PASS
- 記事内容が装置用途に一致: PASS
- 関連論文ページ遷移可否: PASS
- 追加所見: Chrome 上に Codex の権限ポップアップが重なったが、root と beginner route の URL hash、機器名、目次、原理見出し、試料見出し、背景シート表示は視認できた。配信 bootstrap は web.app / firebaseapp.com で同一 version を確認した。

## Verification Integrity
- 検証中スクリプト使用回数（必ず0）: 0
- 手作業確認URL一覧:
  - https://kikidoko.web.app/
  - https://kikidoko.web.app/data/bootstrap-v1.json
  - https://kikidoko.firebaseapp.com/data/bootstrap-v1.json
  - https://kikidoko.web.app/#/beginner/2tQSyysW5GzUbZBLqC9k
  - https://kikidoko.web.app/#/beginner/YOyGKvBvvqYAzXGWjO8R
  - https://kikidoko.web.app/#/beginner/d1chcYWvdrO4bm83FPKp
  - https://kikidoko.web.app/data/equipment_detail_shards/detail-0f.json
  - https://kikidoko.web.app/data/equipment_detail_shards/detail-17.json
  - https://kikidoko.web.app/data/equipment_detail_shards/detail-21.json
  - https://kikidoko.web.app/data/equipment_detail_shards/detail-2a.json
  - https://kikidoko.web.app/data/equipment_detail_shards/detail-23.json
- 手作業確認時刻一覧:
  - 2026-03-21 09:37:18 JST root
  - 2026-03-21 09:37:47 JST beginner freezer
  - 2026-03-21 09:38:14 JST beginner lab C-1
  - 2026-03-21 09:38:34 JST beginner micro logger

## Final Decision
- 判定（PASS/FAIL）: PASS
- FAIL時の是正内容: なし
- 次アクション: manual_guard close を実行して cycle0043 を完了扱いにする
