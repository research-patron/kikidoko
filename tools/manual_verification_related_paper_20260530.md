# Manual Verification: RELATED-PAPER-GUIDE-100

- サイクルID: `RELATED-PAPER-GUIDE-100`
- 検証者: `codex-manual`
- 検証日: `2026-05-30`

## Deployment Status
- 本番URL: `https://kikidoko.org/data/bootstrap-v1.json`
- 更新情報URL: `https://kikidoko.org/update-info/index.json`
- 参照バージョン文字列: `2026-05-30T09:08:20.098514+00:00`
- 配信確認時刻: `2026-05-30 23:53:42 JST`
- bootstrap version/generated_at 一致: `PASS`
- update-info latest: `2026-05-30-related-paper-data`

## Target Equipments
- 対象件数: `100`
- 確認 detail shard 数: `50`
- 確認 shard: `00, 01, 02, 03, 04, 05, 06, 07, 08, 09, 0a, 10, 11, 12, 13, 14, 18, 19, 1a, 1b, 1c, 1d, 1f, 20, 21, 22, 23, 24, 26, 29, 2b, 2c, 2d, 2e, 2f, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 3a, 3b, 3d, 3e, 3f`

## Live Publish Verification (CLI)
- 確認した detail shard URL: `https://kikidoko.org/data/equipment_detail_shards/detail-<shard>.json`
- 対象 doc_id が shard に存在: `PASS (100/100)`
- `manual_content_v1.review.reviewer=codex-manual`: `PASS`
- `reviewed_at` 非空: `PASS`
- `beginner_guide.principle_ja` 存在: `PASS`
- `beginner_guide.sample_guidance_ja` 存在: `PASS`
- `beginner_guide.basic_steps_ja` 存在: `PASS`
- `beginner_guide.common_pitfalls_ja` 存在: `PASS`
- `paper_explanations` 存在: `PASS`
- 追加所見: `live detail shard check: checked=100 / fail=0`

## Verification Integrity
- 検証中スクリプト使用回数（必ず0）: `0`
- 確認した公開URL一覧:
  - `https://kikidoko.org/data/bootstrap-v1.json`
  - `https://kikidoko.org/update-info/index.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-00.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-01.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-02.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-03.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-04.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-05.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-06.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-07.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-08.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-09.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-0a.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-10.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-11.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-12.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-13.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-14.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-18.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-19.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-1a.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-1b.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-1c.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-1d.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-1f.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-20.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-21.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-22.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-23.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-24.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-26.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-29.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-2b.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-2c.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-2d.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-2e.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-2f.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-30.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-31.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-32.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-33.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-34.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-35.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-36.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-37.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-38.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-39.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-3a.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-3b.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-3d.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-3e.json`
  - `https://kikidoko.org/data/equipment_detail_shards/detail-3f.json`
- 手作業確認時刻一覧: `2026-05-30 23:48-23:53 JST`

## Final Decision
- 判定（PASS/FAIL）: `PASS`
- FAIL時の是正内容: `なし`
- 次アクション: `完了`
