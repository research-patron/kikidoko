# Manual Verification - CYCLE-REBUILD-0007

- Verification date: 2026-03-07
- Verification time: 2026-03-07 19:37-19:42 JST
- Verification phase Python/Node script usage: 0
- Verification method: live Hosting release check with `firebase` and direct content inspection with `curl` on production JSON endpoints
- Hosting URL: https://kikidoko.web.app
- Firebaseapp URL: https://kikidoko.firebaseapp.com
- Live release time: 2026-03-07T10:37:40.946Z
- Bootstrap generated_at: 2026-03-07T10:35:49.169677+00:00

## Checked URLs
- https://kikidoko.web.app/data/bootstrap-v1.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-3a.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-07.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-30.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-2e.json

## Checked items
1. KUMAMOTO-list3f-03 / 実体顕微鏡 ライカマイクロシステムズ M205C
- review.status: approved
- general_usage.summary_ja: present
- beginner_guide principle/basic_steps/common_pitfalls: present
- paper_explanations: present
- Result: PASS

2. SvQRc4JuKTgLcTu1rsJh / 金スパッタリング・カーボン蒸着装置 株式会社日立ハイテクノロジーズ E-1010
- review.status: approved
- general_usage.summary_ja: present
- beginner_guide principle: present
- paper_explanations: present
- Result: PASS

3. KUMAMOTO-list3f-02 / 断面イオンミリング 株式会社日立ハイテクノロジーズ E-3500
- review.status: approved
- general_usage.summary_ja: present
- beginner_guide principle/basic_steps/common_pitfalls: present
- paper_explanations: present
- Result: PASS

4. KUMAMOTO-list3f-08 / ユニバーサルズーム顕微鏡 株式会社ニコンインステック MULTIZOOM AZ100
- review.status: approved
- general_usage.summary_ja: present
- beginner_guide principle/basic_steps/common_pitfalls: present
- paper_explanations: present
- Result: PASS

## Note on duplicate row
- KUMAMOTO-list3f-07 is still present as a raw pending duplicate row in live shard data.
- The approved counterpart SvQRc4JuKTgLcTu1rsJh for the same equipment_id KUMAMOTO-list3f-07 is live and contains the curated content.
- Current display policy is approved-priority resolution.

## Final result
- Manual verification result: PASS
