# CYCLE-REBUILD-0032 repair100 Manual Verification

- Cycle: `CYCLE-REBUILD-0032 repair100`
- Verification phase script usage: `0`
- Manual verification window: `2026-03-20 17:12 JST - 2026-03-20 17:13 JST`
- Result: `PASS`
- Live release time: `2026-03-20 17:12:29 JST`
- Bootstrap version: `2026-03-20T08:08:20.200654+00:00`

## Checked URLs
- https://kikidoko.web.app/
- https://kikidoko.web.app/data/bootstrap-v1.json
- https://kikidoko.firebaseapp.com/data/bootstrap-v1.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-3f.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-31.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-2d.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-11.json

## Checked Docs
1. `eqnet-4207` スピンコーター(U13 MS-A150) ミカサ(MS-A150)
2. `eqnet-2056` スプレーコーター((株)三明・DC120)
3. `eqnet-5285` スライドスキャナー Olympus VS200 Olympus(SLIDEVIEW VS200)
4. `eqnet-1949` セクショニング光学顕微鏡 DeltaVision S/N : pd12562

## Manual Checks
- `web.app` / `firebaseapp.com` とも bootstrap version が `2026-03-20T08:08:20.200654+00:00` で一致
- 代表4件で `manual_content_v1.review.status=approved` を確認
- 代表4件で初心者ガイドの4セクションが存在することを確認
- 判定: `PASS`
