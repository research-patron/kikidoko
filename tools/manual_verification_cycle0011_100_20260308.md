# CYCLE-REBUILD-0011 Manual Verification

- Verification phase Python/Node scripts used: 0
- Checked at: 2026-03-08 21:27:09 JST - 2026-03-08 21:29:15 JST
- Result: PASS

## Live deployment
- https://kikidoko.web.app
- https://kikidoko.firebaseapp.com

## Checked URLs
- https://kikidoko.web.app/
- https://kikidoko.web.app/data/bootstrap-v1.json
- https://kikidoko.web.app/data/equipment_snapshot_lite-v1.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-00.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-32.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-2b.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-3f.json
- https://kikidoko.firebaseapp.com/data/bootstrap-v1.json

## Checked equipment
1. Q150RES スパッタコーター
2. 高分解能核磁気共鳴装置（400 MHz NMR）
3. 分光エリプソメーター(Sentec)
4. 原子間力顕微鏡装置(AFM)

## Manual checks
- root HTML served current patch asset references.
- bootstrap-v1.json generated_at matched the latest deployment timestamp range.
- Representative detail shards returned review.status=approved.
- Beginner guide contained principle, sample guidance, steps, and pitfalls for each checked item.
