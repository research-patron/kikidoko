# Manual Verification Checklist: CYCLE-REBUILD-0021

- Verification phase Python/Node script usage: 0
- Verification time: 2026-03-12 22:44 JST - 2026-03-12 22:47 JST
- Hosting live release time: 2026-03-12T11:45:14.454Z
- Hosting URL: https://kikidoko.web.app
- Firebaseapp URL: https://kikidoko.firebaseapp.com
- Bootstrap version: 2026-03-12T11:40:47.740761+00:00
- Result: PASS

## Checked URLs
- https://kikidoko.web.app/
- https://kikidoko.web.app/data/bootstrap-v1.json
- https://kikidoko.firebaseapp.com/data/bootstrap-v1.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-0d.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-3c.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-07.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-28.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-06.json

## Checked representative equipment
- eqnet-5403 フローサイトメーター・セルソータ―(ベクトン・ディッキンソン FACS DiscoverS8)
- eqnet-2720 紫外可視分光光度計(日本分光・V-550)
- eqnet-3710 ガンマカウンター (PerkinElmer, 2480 Wizard)
- FgaJTbAFifzkSZc8MuMR EB蒸着装置
- eqnet-3782 JEOL 400 MHz NMR (ECZ-400R)

## Manual findings
- web.app と firebaseapp.com の bootstrap version はともに `2026-03-12T11:40:47.740761+00:00` を返した。
- live release time は `2026-03-12T11:45:14.454Z` へ更新されていた。
- 代表5件はすべて `manual_content_v1.review.status = approved` を返した。
- 代表5件の beginner guide は空白除外 `2000-3000字` を満たしていた。
- 代表5件の論文解説は空でなく、初心者ガイド4セクションも揃っていた。
