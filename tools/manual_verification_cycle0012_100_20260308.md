# CYCLE-REBUILD-0012 Manual Verification

- Verification phase Python/Node scripts used: 0
- Checked at: 2026-03-08 22:12:12 JST - 2026-03-08 22:17:30 JST
- Result: PASS

## Live deployment
- https://kikidoko.web.app
- https://kikidoko.firebaseapp.com

## Checked URLs
- https://kikidoko.web.app/
- https://kikidoko.web.app/data/bootstrap-v1.json
- https://kikidoko.web.app/data/equipment_snapshot_lite-v1.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-08.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-10.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-22.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-1b.json
- https://kikidoko.firebaseapp.com/data/bootstrap-v1.json

## Checked equipment
1. 3D/4D蛍光画像解析ソフトウェア
2. 400 MHz 核磁気共鳴装置 (Bruker社製・AVANCE III)
3. オールインワン蛍光顕微鏡 (KEYENCE BZ-8000)
4. 超純水装置(Direct-Q UV 3) MERCK(Direct-Q UV3)

## Manual checks
- root HTML served current patch asset references.
- bootstrap-v1.json generated_at matched the latest deployment timestamp range.
- Representative detail shards returned review.status=approved.
- Beginner guide contained principle, sample guidance, steps, and pitfalls for each checked item.
