# CYCLE-REBUILD-0038 Manual Verification

- batch_id: `BATCH-20260320-CYCLE0038-REPAIR100`
- verification_result: `PASS`
- verification_window: `2026-03-20 18:40 JST - 2026-03-20 18:41 JST`
- verification_phase_python_node_script_runs: `0`
- live_release_time: `2026-03-20 18:39:37 JST`
- bootstrap_version: `2026-03-20T09:34:46.057205+00:00`
- bootstrap_generated_at: `2026-03-20T09:34:46.057205+00:00`

## Gate Summary
- audit_manual_authenticity full100: `PASS`
- verify_requirement_100 subset functional: `PASS`
- verify_requirement_100 subset strict_content: `PASS`
- ui_smoke_manual_routes: `PASS`
- manual_guard close: `PASS`

## Manual URLs
- [root](https://kikidoko.web.app/)
- [bootstrap-v1.json(web.app)](https://kikidoko.web.app/data/bootstrap-v1.json)
- [bootstrap-v1.json(firebaseapp)](https://kikidoko.firebaseapp.com/data/bootstrap-v1.json)
- [detail-0a.json](https://kikidoko.web.app/data/equipment_detail_shards/detail-0a.json)
- [detail-20.json](https://kikidoko.web.app/data/equipment_detail_shards/detail-20.json)
- [detail-3e.json](https://kikidoko.web.app/data/equipment_detail_shards/detail-3e.json)
- [detail-2e.json](https://kikidoko.web.app/data/equipment_detail_shards/detail-2e.json)
- [detail-14.json](https://kikidoko.web.app/data/equipment_detail_shards/detail-14.json)

## Verified Representative Docs
1. `Uws7Nd0FITQFhBuZ6UX3` `超遠心機 －型式： himac CP100WX`
2. `482ergQpZB21JJEsNXxy` `卓上タンパク質合成システム－型式：Protemist DT`
3. `pKbqSe700ZzWohdFw65n` `ツインドライブ型レオメータ(YG-001)`
4. `n8KsCALgOq9rNk6K1yah` `ユニバーサルズーム顕微鏡 株式会社ニコンインステック MULTIZOOM AZ100`
5. `zi1yT7fU9lLrsbZCUane` `ﾏｲｸﾛﾌﾟﾚｰﾄｼﾝﾁﾚｰｼｮﾝ・ﾙﾐﾈｯｾﾝｽｶｳﾝﾀｰ－型式：TopCount NXT`

## Live Checks
- web.app bootstrap version/generation matched local deploy output
- firebaseapp bootstrap version/generation matched web.app
- representative detail shards exposed `manual_content_v1.review.status=approved`
- representative detail shards exposed `principle_ja`, `sample_guidance_ja`, `basic_steps_ja`, `common_pitfalls_ja`

## Repair History
- initial final-10 apply failed on cross-document similarity
- repair5 similarity queue addressed:
  - `AKe01kSAVYjDCOFi2AG0`
  - `0pBWvk4yD9M6MGBtHvw4`
  - `gr3Vcqj6vgJw9QXBkJHH`
  - `JKJelUiKor4fkn6WYRYB`
  - `a7B5vrLrCzcl2DqCdLfU`
- remaining pair `MnKJOOuDLNYBS9hFiUEq` / `a7B5vrLrCzcl2DqCdLfU` was isolated
- repair1 similarity queue rewrote `a7B5vrLrCzcl2DqCdLfU`
- main repair100 queue row for `a7B5vrLrCzcl2DqCdLfU` was synchronized from current snapshot before final reapply
- final full100 audit reached `guide_high_similarity_pairs=0`

## Counts
- approved: `1470`
- pending: `9128`
- rejected: `0`
- total: `10598`
