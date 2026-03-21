# Manual Verification Log

- cycle: CYCLE-REBUILD-0016-REDO
- batch_id: BATCH-20260311-CYCLE0016-REDO-100-REPAIR2
- verification_phase_python_node_script_usage: 0
- verification_start_jst: 2026-03-11 12:52:00 JST
- verification_end_jst: 2026-03-11 12:57:00 JST
- verdict: PASS

## Checked URLs
- https://kikidoko.web.app/
- https://kikidoko.web.app/data/bootstrap-v1.json
- https://kikidoko.firebaseapp.com/data/bootstrap-v1.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-33.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-37.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-2e.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-04.json

## Manual Checks
- `web.app` と `firebaseapp.com` の `bootstrap-v1.json` がともに `version=2026-03-11T03:47:40.723103+00:00` を返すことを確認。
- `eqnet-977` の live detail で `manual_content_v1.review.status=approved`、`JNM-ECZL500` を明示した固有の step1 と sample guidance を確認。
- `eqnet-2329` の live detail で `manual_content_v1.review.status=approved`、`セルアナライザー EC800` を明示した固有の step1 と pitfalls を確認。
- `eqnet-2200` の live detail で `manual_content_v1.review.status=approved`、`HUS-5GB` の観察前処理に寄せた sample guidance と固有 step1 を確認。
- `eqnet-4202` の live detail で `manual_content_v1.review.status=approved`、`MX50A/T` の撮像条件固定を含む固有の principle と sample guidance を確認。
- 上記4件はいずれも beginner guide 4セクションが存在し、duplicate group 修正後の固有表現が live に反映されていることを確認。
