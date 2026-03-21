# CYCLE-REBUILD-0034 repair100 Manual Verification

- 検証フェーズでのPython/Nodeスクリプト使用: 0回
- 手作業確認時刻: 2026-03-20 17:34 JST - 2026-03-20 17:38 JST
- 手作業確認の判定結果: PASS
- Firebase Hosting live release: 2026-03-20 17:34:26 JST
- bootstrap version/generated_at: 2026-03-20T08:30:36.740389+00:00

## 手作業確認URL
- https://kikidoko.web.app/
- https://kikidoko.web.app/data/bootstrap-v1.json
- https://kikidoko.firebaseapp.com/data/bootstrap-v1.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-2c.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-01.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-0e.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-1d.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-10.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-11.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-05.json

## 確認した代表機器
1. eqnet-4778 分注機 Multidrop Combi (1-3F) Thermo Scientific(Multidrop Combi)
2. eqnet-4115 分離用超遠心機CP80WX 日立工機(himac CP80WX)
3. eqnet-3387 加熱気化水銀測定装置(MA-3000)
4. eqnet-3733 動物隔離用アイソレーションラック FRPバイオ2000フィルターユニット CL5608-1S CL-5623
5. eqnet-3411 卓上型全反射蛍光X線分析装置(リガク:ナノハンターII)
6. sB39y0rUJPD869tg6Xrh 次世代シーケンサーNextSeq2000
7. MUGIOGQ0fn1X3LiDvotO 次世代シーケンサーNextSeq500

## メモ
- web.app / firebaseapp.com の bootstrap version は一致
- 代表確認した 7 件は live shard 上で manual_content_v1.review.status=approved
- 初心者ガイドの principle / sample_guidance / basic_steps / common_pitfalls が live shard 上で確認できた
- NextSeq2000 / NextSeq500 の similarity 修正後 live 反映を確認
