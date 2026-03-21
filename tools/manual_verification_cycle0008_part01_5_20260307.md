# Manual Verification - CYCLE-REBUILD-0008 PART01

- Verification date: 2026-03-07
- Verification time: 2026-03-07 21:11-21:16 JST
- Verification phase Python/Node script usage: 0
- Verification method: live Hosting release check with `firebase` and direct inspection of production shard JSON via `curl`
- Hosting URL: https://kikidoko.web.app
- Firebaseapp URL: https://kikidoko.firebaseapp.com
- Live release time: 2026-03-07T12:15:57.371Z
- Bootstrap generated_at: 2026-03-07T12:14:52.120953+00:00

## Checked URLs
- https://kikidoko.web.app/data/bootstrap-v1.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-07.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-11.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-35.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-30.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-3f.json

## Checked items
1. KUMAMOTO-list3f-07 / 金スパッタリング・カーボン蒸着装置 株式会社日立ハイテクノロジーズ E-1010
- review.status: approved
- summary present
- beginner principle present
- paper_explanations count: 1
- Result: PASS

2. KUMAMOTO-list3f-01 / 電子線マイクロアナライザ 株式会社島津製作所 EPMA-1720H
- review.status: approved
- summary present
- beginner principle present
- paper_explanations count: 1
- Result: PASS

3. KUMAMOTO-list3f-09 / 集束イオンビーム (Focused Ion Beam) 株式会社日立ハイテクノロジーズ NB5000
- review.status: approved
- summary present
- beginner principle present
- paper_explanations count: 2
- Result: PASS

4. 2BJbNIWamHA1K1YpVej6 / 液体ｼﾝﾁﾚｰｼｮﾝｶｳﾝﾀｰ－型式：LSC-6100
- review.status: approved
- summary present
- beginner principle present
- paper_explanations count: 1
- Result: PASS

5. KUMAMOTO-list4f-08 / イオンスパッタリング装置 日本電子株式会社 JFC-1100E
- review.status: approved
- summary present
- beginner principle present
- paper_explanations count: 2
- Result: PASS

## Final result
- Manual verification result: PASS
