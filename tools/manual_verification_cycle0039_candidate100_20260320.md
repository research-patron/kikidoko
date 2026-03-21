# CYCLE-REBUILD-0039 Candidate100 Manual Verification

- Batch: `BATCH-20260320-CYCLE0039-CANDIDATE100`
- Verification phase script usage: `0`
- Manual verification start: `2026-03-20 21:31:18 JST`
- Manual verification end: `2026-03-20 21:33:35 JST`
- Result: `PASS`

## Distribution Check
- `firebase hosting:channel:list` live release: `2026-03-20 21:30:40 JST`
- `web.app bootstrap`: `2026-03-20T12:25:23.597347+00:00`
- `firebaseapp bootstrap`: `2026-03-20T12:25:23.597347+00:00`

## Checked URLs
- https://kikidoko.web.app/
- https://kikidoko.web.app/data/bootstrap-v1.json
- https://kikidoko.firebaseapp.com/data/bootstrap-v1.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-20.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-35.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-09.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-3e.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-3b.json

## Representative Documents
1. `eBBjZr2ViN0O11xevMwv` Gene Pulser Xcellコンプリートシステム165-2660J1
2. `eqnet-1181` フローサイトメーター(自動細胞分析装置) Becton Dickenson FACS Calibur
3. `eqnet-2122` 赤外・ラマン分光装置(バリアン 670/610-IR)
4. `eqnet-3061` 共焦点レーザー走査型顕微鏡 LSM880+AiryscanFast
5. `eqnet-3033` 液体クロマトグラフ(島津製作所・LC-10 VC)

## Notes
- Root and bootstrap endpoints returned `200`.
- Representative detail shards contained target `doc_id` values.
- Representative detail shards exposed `manual_content_v1.review.status=approved` and the four beginner guide sections.
