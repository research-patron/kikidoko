# CYCLE-REBUILD-0033 repair100 Manual Verification

- 検証フェーズでのPython/Nodeスクリプト使用: 0回
- 手作業確認時刻: 2026-03-20 17:20 JST - 2026-03-20 17:22 JST
- 手作業確認の判定結果: PASS
- Firebase Hosting live release: 2026-03-20 17:20:36 JST
- bootstrap version: 2026-03-20T08:15:54.194441+00:00
- bootstrap generated_at: 2026-03-20T08:15:54.194441+00:00

## 手作業確認URL
1. https://kikidoko.web.app/
2. https://kikidoko.web.app/data/bootstrap-v1.json
3. https://kikidoko.firebaseapp.com/data/bootstrap-v1.json
4. https://kikidoko.web.app/data/equipment_detail_shards/detail-32.json
5. https://kikidoko.web.app/data/equipment_detail_shards/detail-37.json
6. https://kikidoko.web.app/data/equipment_detail_shards/detail-05.json
7. https://kikidoko.web.app/data/equipment_detail_shards/detail-29.json
8. https://kikidoko.web.app/data/equipment_detail_shards/detail-0a.json

## 確認した代表機器
1. eqnet-2430 プロテインシーケンサ (SHIMADZU・PPSQ-51A)
2. eqnet-613 プロテインシーケンサー (Shimadzu PPSQ-31A)
3. eqnet-819 プロテオーム前処理サービス
4. eqnet-1938 プローブ顕微鏡 JEOL JSPM-5200
5. eqnet-853 ペプチドシーケンサー(島津制作所製・PPSQ-33A)

## 手作業確認メモ
- web.app / firebaseapp.com の bootstrap version は一致
- 代表5件で manual_content_v1.review.status=approved を確認
- 代表5件で beginner_guide の principle / sample_guidance / basic_steps / common_pitfalls を確認
