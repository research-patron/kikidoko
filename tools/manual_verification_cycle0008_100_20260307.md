# Manual Verification Log

- cycle_id: CYCLE-REBUILD-0008
- scope: 100 items reflected
- verification_phase_script_usage_python_node: 0
- verified_at: 2026-03-07 23:56:06 JST
- deployment_target: https://kikidoko.web.app
- deployment_mirror_check: https://kikidoko.student-subscription.com

## Deployment State
- live releaseTime: 2026-03-07T14:43:06.946Z
- root URL: https://kikidoko.web.app/
- bootstrap URL: https://kikidoko.web.app/data/bootstrap-v1.json
- root asset version observed: v=20260306-bootstrap-sync-1
- bootstrap generated_at observed: 2026-03-07T14:37:21.268244+00:00

## Manual Checks
1. https://kikidoko.web.app/data/equipment_detail_shards/detail-07.json
- target: KUMAMOTO-list3f-07
- review.status: approved
- beginner guide principle present: yes
- paper_explanations count: 1
- note: single explanation is acceptable for this row because the live row exposes one linked paper explanation.

2. https://kikidoko.web.app/data/equipment_detail_shards/detail-11.json
- target: U1BUr0RTkKrPe7NAznny
- review.status: approved
- beginner guide principle present: yes
- paper_explanations count: 2

3. https://kikidoko.web.app/data/equipment_detail_shards/detail-11.json
- target: sB39y0rUJPD869tg6Xrh
- review.status: approved
- beginner guide principle present: yes
- paper_explanations count: 2

4. https://kikidoko.web.app/data/equipment_detail_shards/detail-1d.json
- target: TOKUSHIMA-59
- review.status: approved
- beginner guide principle present: yes
- paper_explanations count: 2

## Mirror Domain
- https://kikidoko.student-subscription.com/
- curl result from this environment: could not resolve host
- primary deployment verification therefore used web.app live

## Final Judgement
- manual_check_result: PASS
