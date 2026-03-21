# Manual Verification Log: CYCLE-REBUILD-0037 repair100

- Batch: `BATCH-20260320-CYCLE0037-REPAIR100`
- Verification window: `2026-03-20 18:19 JST - 2026-03-20 18:21 JST`
- Verification method: browser direct open + single-shot `firebase` / `curl` checks
- Python/Node script usage during verification: `0`
- Result: `PASS`

## Distribution Status
- `firebase hosting:channel:list --project kikidoko --site kikidoko`
  - live release: `2026-03-20 18:19:22 JST`
  - live URL: `https://kikidoko.web.app`
- `bootstrap-v1.json`
  - `web.app`: `version=2026-03-20T09:13:55.998636+00:00`, `generated_at=2026-03-20T09:13:55.998636+00:00`
  - `firebaseapp.com`: `version=2026-03-20T09:13:55.998636+00:00`, `generated_at=2026-03-20T09:13:55.998636+00:00`

## Manually Checked URLs
1. `https://kikidoko.web.app/`
2. `https://kikidoko.web.app/data/bootstrap-v1.json`
3. `https://kikidoko.firebaseapp.com/data/bootstrap-v1.json`
4. `https://kikidoko.web.app/data/equipment_detail_shards/detail-34.json`
5. `https://kikidoko.web.app/data/equipment_detail_shards/detail-1d.json`
6. `https://kikidoko.web.app/data/equipment_detail_shards/detail-13.json`
7. `https://kikidoko.web.app/data/equipment_detail_shards/detail-2b.json`
8. `https://kikidoko.web.app/data/equipment_detail_shards/detail-3f.json`

## Representative Equipment Checks
- `oCRETqgx0aduVoPDIQEH` `紫外可視分光光度計－型式： BioSpectrometer kinetic`
  - shard: `detail-34.json`
  - review status: `approved`
  - beginner guide lengths: `principle=593`, `sample=568`, `steps=6`, `pitfalls=5`
- `TOKUSHIMA-72` `光造形3Dプリンタ`
  - shard: `detail-1d.json`
  - review status: `approved`
  - beginner guide lengths: `principle=495`, `sample=854`, `steps=6`, `pitfalls=6`
- `vLxG7JK9l1a27ArfGbY1` `全自動タンパク質合成システム－型式：GenDecorder`
  - shard: `detail-13.json`
  - review status: `approved`
  - beginner guide lengths: `principle=577`, `sample=808`, `steps=6`, `pitfalls=6`
- `qhoCPKqqubZ0uyaZfJFq` `X線非破壊検査装置(YG-602)`
  - shard: `detail-2b.json`
  - review status: `approved`
  - beginner guide lengths: `principle=656`, `sample=673`, `steps=6`, `pitfalls=4`
- `KUMAMOTO-list3f-06` `プラズマクリーナー YHS-R`
  - shard: `detail-3f.json`
  - review status: `approved`
  - beginner guide lengths: `principle=781`, `sample=265`, `steps=6`, `pitfalls=4`

## Count Snapshot
- `approved=1470`
- `pending=9128`
- `rejected=0`
- `missing=0`
- `total=10598`

## Notes
- Verification phase used no Python/Node execution.
- Live `bootstrap-v1.json` versions matched between `web.app` and `firebaseapp.com`.
- Representative live shard items exposed `manual_content_v1.review.status=approved` and populated beginner guide sections.
