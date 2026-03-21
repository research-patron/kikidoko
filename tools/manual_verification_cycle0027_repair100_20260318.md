# Manual Verification - CYCLE-REBUILD-0027 repair100

- Verification phase Python/Node script usage: 0
- Verification method: manual inspection via firebase/curl/jq of live Hosting payloads
- Verification start: 2026-03-18 07:29:51 JST
- Verification end: 2026-03-18 07:30:12 JST
- Live release time: 2026-03-18 07:26:05 JST
- Live bootstrap version: 2026-03-17T22:24:42.706873+00:00
- Result: PASS

## Checked URLs
1. https://kikidoko.web.app/
2. https://kikidoko.web.app/data/bootstrap-v1.json
3. https://kikidoko.firebaseapp.com/data/bootstrap-v1.json
4. https://kikidoko.web.app/data/equipment_detail_shards/detail-11.json
5. https://kikidoko.web.app/data/equipment_detail_shards/detail-0a.json
6. https://kikidoko.web.app/data/equipment_detail_shards/detail-18.json

## Checked equipment
1. 6gYvmotIilCkDzCoazNd / DNAシーケンサー3130xl-L
   - review.status=approved
   - reviewer=codex-manual
   - reviewed_at=2026-03-18T01:10:01+00:00
   - basic_steps_ja[1] present and unique to left baseline workflow
   - common_pitfalls_ja[1] present and unique to left baseline workflow
2. W8F1EJB9RfmLb53Kr4VE / DNAシーケンサー3130xl-R
   - review.status=approved
   - reviewer=codex-manual
   - reviewed_at=2026-03-18T01:10:02+00:00
   - basic_steps_ja[1] present and unique to restart stabilization workflow
   - common_pitfalls_ja[1] present and unique to restart stabilization workflow
3. 4bdeB49BlNRyCkhE3KGp / DNAシーケンサー3500xL
   - review.status=approved
   - reviewer=codex-manual
   - reviewed_at=2026-03-18T01:10:03+00:00
   - basic_steps_ja[1] present and unique to multi-sample plate workflow
   - common_pitfalls_ja[1] present and unique to column/block control workflow
4. I2EoqGndscKRyNBWbyFS / DNAシーケンサー（セルフラン） (ABI 3130xl)
   - review.status=approved
   - reviewer=codex-manual
   - reviewed_at=2026-03-18T01:10:04+00:00
   - basic_steps_ja[1] present and unique to self-run startup workflow
   - common_pitfalls_ja[1] present and unique to post-run wash handoff workflow
