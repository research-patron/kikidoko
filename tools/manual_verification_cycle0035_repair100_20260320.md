# CYCLE-REBUILD-0035 repair100 Manual Verification

- 検証フェーズでのPython/Nodeスクリプト使用: 0回
- 手作業確認時刻: 2026-03-20 17:51 JST - 2026-03-20 17:52 JST
- 手作業確認の判定結果: PASS
- Firebase Hosting live release: 2026-03-20 17:51:00 JST
- bootstrap version/generated_at: 2026-03-20T08:46:53.386232+00:00

## 手作業確認URL
- https://kikidoko.web.app/
- https://kikidoko.web.app/data/bootstrap-v1.json
- https://kikidoko.firebaseapp.com/data/bootstrap-v1.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-2b.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-27.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-32.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-13.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-04.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-2d.json
- https://kikidoko.web.app/data/equipment_detail_shards/detail-3d.json

## 確認した代表機器
1. vieiUkG0CMYeiZrZIfnw 熱重量・熱量同時測定装置（TG-DTA/DSC）
2. eqnet-3395 熱重量・示差熱分析装置(Thermo plus EVO2 TG-DTA/H-SL)
3. eqnet-1204 熱重量・示差熱分析装置(リガクThermo Plus EvoII)
4. tmlqi7J1w3ULrWSoRnPe 熱電放出型走査電子顕微鏡（SEM）
5. eqnet-2065 燃料電池性能試験装置(Solartron・12528PBI)
6. MIE-equipment3 試料水平型多目的X線回折測定装置（XRD）
7. MIE-equipment10 走査型X線光電子分光分析装置 （多モードトポ解析システム/XPS）

## メモ
- web.app / firebaseapp.com の bootstrap version は一致
- 代表確認した 7 件は live shard 上で manual_content_v1.review.status=approved
- 初心者ガイドの principle / sample_guidance / basic_steps / common_pitfalls を live shard 上で確認
- MIE-equipment3 / MIE-equipment10 の similarity 修正後 live 反映を確認
