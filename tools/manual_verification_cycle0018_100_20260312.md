# Manual Verification - CYCLE-REBUILD-0018

- Verification phase Python/Node script usage: 0
- Manual verification window: 2026-03-12 08:41 JST - 2026-03-12 08:45 JST
- Deploy release: 2026-03-12 08:40:29 JST
- Result: PASS

## Deployment state
- https://kikidoko.web.app/data/bootstrap-v1.json
- https://kikidoko.firebaseapp.com/data/bootstrap-v1.json
- Both endpoints returned `version=2026-03-11T23:36:47.928801+00:00`.

## Manual checks
1. https://kikidoko.web.app/
- Live hosting reachable.

2. https://kikidoko.web.app/data/equipment_detail_shards/detail-1c.json
- Confirmed `doc_id=y8Ui46jeOMsXNX7ANJvd`.
- Name: `旭町ラボ オープンラボスペース 202実験室(B)-1`
- `manual_content_v1.review.status=approved`
- beginner guide present with steps/pitfalls populated.

3. https://kikidoko.web.app/data/equipment_detail_shards/detail-16.json
- Confirmed `doc_id=zbY4qgZK4bjNMYHGepyh`.
- Name: `3Dプリンタ Form3`
- `manual_content_v1.review.status=approved`
- paper explanations and beginner guide present.

4. https://kikidoko.web.app/data/equipment_detail_shards/detail-26.json
- Confirmed `doc_id=OAKDtGP8660BvXJUMMcH`.
- Name: `PAM-2500`
- `manual_content_v1.review.status=approved`
- general usage summary and beginner guide present.

5. https://kikidoko.web.app/data/equipment_detail_shards/detail-08.json
- Confirmed `doc_id=sD7awrsVJpNHKyknxOEi`.
- Name: `フラッシュ自動精製システム`
- `manual_content_v1.review.status=approved`
- paper explanations and beginner guide present.
