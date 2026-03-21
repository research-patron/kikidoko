# Manual Verification Log

- サイクルID: LIVE-BOOTSTRAP-SYNC-20260306
- 検証者: codex-manual
- 検証日: 2026-03-06 JST

## Deployment Status
- 本番URL (web.app): https://kikidoko.web.app
- 本番URL (firebaseapp.com): https://kikidoko.firebaseapp.com
- 参照バージョン文字列: `20260306-bootstrap-sync-1`
- 配信確認時刻: 2026-03-06 23:58-24:06 JST

## Target Equipments
- `YpiYi5rGQqcX6ofJF4lt`
  - 機器名: DNAシーケンサー －型式： Spectrum Compact CE System
  - 確認URL: https://kikidoko.web.app/data/equipment_detail_shards/detail-32.json?v=20260306-bootstrap-sync-1
- `R5b0pxQNyUgJdKFBwK5n`
  - 機器名: NMR(400MHz)－型式：AVANCE 400
  - 確認URL: https://kikidoko.web.app/data/equipment_detail_shards/detail-3d.json?v=20260306-bootstrap-sync-1
- `sjeeh9D6hgUrxujOXjKl`
  - 機器名: NMR(500MHz)－型式：AVANCEⅢHD 500
  - 確認URL: https://kikidoko.web.app/data/equipment_detail_shards/detail-39.json?v=20260306-bootstrap-sync-1

## Manual UI/Data Verification
- `web.app` と `firebaseapp.com` の HTML が `v=20260306-bootstrap-sync-1` を返すことを確認
- `bootstrap-v1.json` の `version/generated_at` が `2026-03-06T14:33:52.867010+00:00` に更新されていることを確認
- `equipment_snapshot_lite-v1.json` の `generated_at` が `2026-03-06T14:33:52.867010+00:00`、`count=10598` であることを確認
- 対象3機器の live detail shard 上で `manual_content_v1.review.status=approved` を確認
- 対象3機器の `beginner_guide.principle_ja` が live JSON に存在し、装置名を含むことを確認

## Verification Integrity
- 検証中スクリプト使用回数（Python/Node）: 0
- 使用した確認手段: `curl` による本番レスポンス確認、目視判定

## Final Decision
- 判定: PASS
- 次アクション: `CYCLE-REBUILD-0003` の手作業検証と guard close を完了後、次の10件へ進行
