# Manual Verification Log: CYCLE-REBUILD-0022

- Verification date: 2026-03-12
- Verification time: 2026-03-12 23:45 JST - 2026-03-12 23:47 JST
- Verification phase Python/Node script usage: 0
- Deployment target: https://kikidoko.web.app
- FirebaseApp mirror: https://kikidoko.firebaseapp.com
- Live release time: 2026-03-12T14:45:12.967Z
- Bootstrap version: 2026-03-12T14:40:19.368951+00:00

## Checked URLs
1. https://kikidoko.web.app/
2. https://kikidoko.web.app/data/bootstrap-v1.json
3. https://kikidoko.firebaseapp.com/data/bootstrap-v1.json
4. https://kikidoko.web.app/data/equipment_detail_shards/detail-38.json
5. https://kikidoko.web.app/data/equipment_detail_shards/detail-2e.json
6. https://kikidoko.web.app/data/equipment_detail_shards/detail-25.json
7. https://kikidoko.web.app/data/equipment_detail_shards/detail-05.json
8. https://kikidoko.web.app/data/equipment_detail_shards/detail-0e.json

## Verified representative equipment
1. eqnet-2978 紫外可視分光光度計(日本分光・V-560)
2. eqnet-2106 ゲルパーミエイションクロマトグラフィ(GPC)
3. eqnet-2147 全自動細胞解析装置(ベックマン・コールター Cytomics FC500)
4. Tef9WwK62flV3dvgdCEv Gene Pulser Xcell エレクトロポレーションシステム
5. Rxrzl5vi6WCgs5JURDon プラズマCVD装置

## Manual checks
- web.app と firebaseapp.com の bootstrap version / generated_at が一致した。
- root HTML は current asset references を返した。
- representative detail shard URLs はすべて HTTP 200 で取得できた。
- CYCLE-REBUILD-0022 の subset requirement / strict audit は PASS 済みで、live deployment 後も bootstrap version が更新されていることを確認した。

## Result
- Manual verification result: PASS
