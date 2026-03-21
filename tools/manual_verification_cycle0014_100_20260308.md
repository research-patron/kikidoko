# Manual Verification Log

- Cycle: CYCLE-REBUILD-0014
- Batch: BATCH-20260308-CYCLE0014-100
- Verification phase Python/Node script usage: 0
- Start: 2026-03-08 23:48:54 JST
- End: 2026-03-08 23:51:09 JST
- Result: PASS

## Release
- Hosting live releaseTime: 2026-03-08T14:48:07.873Z
- WebApp: https://kikidoko.web.app
- FirebaseApp: https://kikidoko.firebaseapp.com

## Checked URLs
- https://kikidoko.web.app/
- https://kikidoko.web.app/data/bootstrap-v1.json
- https://kikidoko.firebaseapp.com/data/bootstrap-v1.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-27.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-2f.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-1e.json

## Representative Checks
1. 400MHz核磁気共鳴装置 (バリアン 400MR)
- doc_id: FKJH26dohbrcjnGbSklE
- review.status: approved
- paper_explanations: 2
- principle_ja の文法破綻文言が除去されていることを確認

2. ライブセルイメージング(Celldiscoverer 7) Zeiss(Celldiscoverer 7)
- doc_id: eqnet-4552
- review.status: approved
- paper_explanations: 2
- 初心者ガイド4セクションの本文が取得できることを確認

3. J-OCTA
- doc_id: eqnet-3812
- review.status: approved
- paper_explanations: 2
- approved 本文と関連論文が live shard に反映されていることを確認

## Notes
- root HTML は patch query `v=20260306-bootstrap-sync-1` を参照
- web.app / firebaseapp.com の bootstrap generated_at は一致
