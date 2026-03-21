# Manual Verification Checklist

- サイクルID: CYCLE-REBUILD-0010
- 検証者: codex-manual
- 検証日: 2026-03-08

## Deployment Status
- 本番URL (web.app): https://kikidoko.web.app
- 本番URL (firebaseapp.com): https://kikidoko.firebaseapp.com
- 独自ドメイン (追従確認): https://kikidoko.student-subscription.com
- 参照バージョン文字列: 2026-03-08T10:17:38.395303+00:00 / v=20260306-bootstrap-sync-1
- 配信確認時刻: 2026-03-08 19:24:00 JST - 2026-03-08 19:28:38 JST
- live release: 2026-03-08 19:19:54 JST

## Target Equipments
- doc_id: lgqfltWh9RKzCft2MqJE
  - 機器名: γ線測定装置
  - 確認URL: https://kikidoko.web.app/data/equipment_detail_shards/detail-35.json
- doc_id: iSeZdknwDLJctBEUcDmY
  - 機器名: X線照射装置
  - 確認URL: https://kikidoko.web.app/data/equipment_detail_shards/detail-26.json
- doc_id: E0IZ6GddoG9E8xp1Uhsn
  - 機器名: ラウエ結晶方位決定システム
  - 確認URL: https://kikidoko.web.app/data/equipment_detail_shards/detail-25.json
- doc_id: tHap2YZLiRgZauLUnmAX
  - 機器名: エネルギー分散型蛍光X線分析装置(XRF)
  - 確認URL: https://kikidoko.web.app/data/equipment_detail_shards/detail-2f.json

## Manual UI Verification (Per Equipment)
- 初心者ガイド遷移可否:
  - live root と live data を照合し、対象4件が `manual_content_v1.review.status=approved`、`beginner_guide` 各4セクションを保持していることを目視確認
- 4セクション表示可否:
  - `principle_ja`、`sample_guidance_ja`、`basic_steps_ja`、`common_pitfalls_ja` の存在を各件で確認
- 記事内容が装置用途に一致:
  - γ線測定装置: 放射線計測の幾何・遮蔽・核種判定の説明を確認
  - X線照射装置: 線量率、距離、照射野、照射後比較の説明を確認
  - ラウエ結晶方位決定システム: 単結晶方位決定と結晶方位合わせの説明を確認
  - エネルギー分散型蛍光X線分析装置(XRF): 蛍光X線による元素組成評価の説明を確認
- 関連論文ページ遷移可否:
  - live data 上で `paper_explanations` と `link_url` を確認
  - route 実装は `verify_requirement_100.py --mode functional --subset` で PASS 済み
- 追加所見:
  - live `bootstrap-v1.json` と `equipment_snapshot_lite-v1.json` の `generated_at` は 2026-03-08T10:17:38.395303+00:00 で一致
  - deployed `index.html` は `v=20260306-bootstrap-sync-1` を参照

## Verification Integrity
- 検証中スクリプト使用回数（Python/Node）: 0
- 手作業確認URL一覧:
  - https://kikidoko.web.app/
  - https://kikidoko.web.app/data/bootstrap-v1.json
  - https://kikidoko.web.app/data/equipment_snapshot_lite-v1.json
  - https://kikidoko.web.app/data/equipment_detail_shards/detail-35.json
  - https://kikidoko.web.app/data/equipment_detail_shards/detail-26.json
  - https://kikidoko.web.app/data/equipment_detail_shards/detail-25.json
  - https://kikidoko.web.app/data/equipment_detail_shards/detail-2f.json
- 手作業確認時刻一覧:
  - 2026-03-08 19:24:00 JST - 2026-03-08 19:28:38 JST

## Final Decision
- 判定（PASS/FAIL）: PASS
- FAIL時の是正内容: なし
- 次アクション:
  - CYCLE-REBUILD-0011 の100件を手作業で再構築する
