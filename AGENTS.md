# Codex Manual Curation Governance (Mandatory)

このファイルは、本リポジトリにおける `manual_content_v1` 手動審査運用の最上位ルールです。  
本ファイルに反する手順・反映・報告は禁止します。

## 0. Startup First Check (Mandatory)
- 作業開始時に必ず `AGENT.md` を開き、その後 `AGENTS.md` 全体を確認すること。
- 検証フェーズでは **Python/Node等のスクリプト実行を禁止** する。
- 検証は Codex 手作業（画面操作・目視確認）で実施すること。
- 検証フェーズでスクリプト実行が発生した場合、その検証結果は無効とし、手作業で再検証すること。

## 1. Non-negotiable
- すべての審査本文は Codex 手作業で個別記述すること。
- 自動生成文の一括投入、同一テンプレ大量展開、時刻一括承認を禁止する。
- 反映前にアテステーション検証を通過しない作業は無効とする。
- 報告前に厳格監査が PASS していない作業は報告禁止とする。

## 2. Prohibited Operations
- 同一文面の大量複製（summary/principle/step1/pitfall1 の重複）
- `reviewed_at` の一括同時刻承認
- reviewer 不一致 (`codex-manual` 以外)
- アテステーション未指定での apply 実行
- 監査 FAIL を無視した報告

## 3. Required Batch Flow
1. Queue 生成（`build_manual_curation_queue.py`）
2. Guard セッション開始（`manual_guard.py start`）
3. 100件手作業入力
4. Apply（10件単位、`--attestation` 必須）
5. 手作業厳格監査（`audit_manual_authenticity.py`）
6. detail shard 再生成（`build_detail_shards.py`）
7. 要件検証（`verify_requirement_100.py`）
8. UIスモーク（`ui_smoke_manual_routes.py`）
9. Guard セッション終了（`manual_guard.py close`）
10. Checkpoint 追記

## 4. Report Gate (Fail Closed)
- 次のすべてが PASS であること:
  - Guard verify
  - 手作業厳格監査
  - requirement 検証
  - UI スモーク
- 報告には次を必ず含めること:
  - `検証フェーズでのスクリプト使用: 0回`
  - 手作業確認したページURL
  - 手作業確認時刻
  - 手作業確認の判定結果（PASS/FAIL）
- 1件でも FAIL がある場合、該当行を `needs_manual_fix` に戻して再実行すること。

## 5. Deviation Handling
- 逸脱を検出した場合は、反映済み変更を無効化し、最小修正で再監査する。
- 再監査 PASS までは checkpoint に「FAIL→修正履歴」を明示する。
- 反映と報告の間に検証結果が変化した場合、必ず再検証を実施する。

## 6. Standard Reviewer / Batch Policy
- reviewer は常に `codex-manual`
- 1バッチは 100件固定（適用は 10件単位）
- `manual_content_v1` 契約は変更しない

## 7. Preflight (Every Batch, Mandatory)
- 作業開始時に次を順に実行すること:
  1. `python3 tools/build_manual_curation_queue.py ... --batch-id <BATCH_ID>`
  2. `python3 tools/manual_guard.py start --batch-id <BATCH_ID> ...`
  3. `python3 tools/manual_guard.py verify --session <SESSION_JSON> ...`
- verify が FAIL の場合、入力/反映を開始してはならない。

## 8. Delivery Gate (Every Batch, Mandatory)
- 報告直前に次を順に実行すること:
  1. `python3 tools/audit_manual_authenticity.py ...`
  2. `python3 tools/verify_requirement_100.py`
  3. 手作業UI検証（ブラウザで対象ページを直接確認。スクリプト自動判定は禁止）
  4. `python3 tools/manual_guard.py close --session <SESSION_JSON> --audit-report <AUDIT_JSON> --requirement-status PASS --ui-status PASS`
- 1つでも FAIL があれば報告禁止。`needs_manual_fix` 化して再実行する。

## 9. Manual Verification Rule (No Script)
- 検証フェーズで禁止:
  - `python*`、`node*`、`*.py`、`*.js` を使った確認処理
  - 自動巡回・自動判定スクリプト
- 検証フェーズで許可:
  - ブラウザの手動操作による確認
  - `firebase` / `curl` 等の単発CLIによる配信状態確認
- 次サイクル開始前の固定フロー:
  1. 配信状態確認（`firebase hosting:channel:list`、`curl` で version 参照）
  2. 手作業UI検証（対象機器をブラウザで直接確認）
  3. `tools/manual_verification_checklist_template.md` に沿って記録保存
  4. すべて PASS の場合のみ次サイクル執筆へ進行

## 10. Development Schedule (Fixed Milestones)
- Phase 0（ガード実装）: 2026-03-01 〜 2026-03-02
- Phase 1（100件パイロット）: 2026-03-03
- Phase 2（本運用）: 2026-03-04 〜 2026-05-01
- 週次目標: 1000件/週（1日2バッチ、週5日）
- マイルストン:
  - 2026-03-06: approved 2600
  - 2026-03-13: approved 3600
  - 2026-03-20: approved 4600
  - 2026-03-27: approved 5600
  - 2026-04-03: approved 6600
  - 2026-04-10: approved 7600
  - 2026-04-17: approved 8600
  - 2026-04-24: approved 9600
  - 2026-05-01: approved 10598 / pending 0
