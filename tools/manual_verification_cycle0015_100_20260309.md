# Manual Verification Log

- cycle: CYCLE-REBUILD-0015
- batch_id: BATCH-20260308-CYCLE0015-100
- verification_phase_python_node_script_usage: 0
- verification_start_jst: 2026-03-09 00:46:21 JST
- verification_end_jst: 2026-03-09 00:48:30 JST
- verdict: PASS

## Checked URLs
- https://kikidoko.web.app/
- https://kikidoko.firebaseapp.com/data/bootstrap-v1.json
- https://kikidoko.web.app/data/bootstrap-v1.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-24.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-04.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-25.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-22.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-2c.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-3a.json

## Manual Checks
- root HTML on `web.app` references the current patch assets and loads without stale path mismatch.
- `bootstrap-v1.json` on `web.app` and `firebaseapp.com` both return `version=2026-03-08T15:44:23.707483+00:00`.
- Representative cycle0015 detail shards return `manual_content_v1.review.status=approved`.
- FTIR pair shows distinct beginner guide content for FT/IR-4100 and FT/IR-6100.
- Shaker pair shows distinct beginner guide content for BR-43FL 2, BR-43FM 2, BR-43FL 4, and BR-43FL 1.
- Representative beginner guide sections include principle, sample guidance, steps, and pitfalls with device-specific wording.
