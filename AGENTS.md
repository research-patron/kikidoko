# Codex Manual Curation Governance (Mandatory)

このファイルは、本リポジトリにおける `manual_content_v1` 手動審査運用の最上位ルールです。  
本ファイルに反する手順・反映・報告は禁止します。

## 0. Startup First Check (Mandatory)
- 作業開始時に必ず `AGENT.md` を開き、その後 `AGENTS.md` 全体を確認すること。
- 検証フェーズでは **Python/Node等のスクリプト実行を禁止** する。
- 検証は Codex 手作業で実施し、live は CLI で公開 JSON を確認すること。
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
8. ローカルUIスモーク（`ui_smoke_manual_routes.py`）
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
  - 確認した公開URL
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
  3. 手作業公開確認（CLI で live の `bootstrap-v1.json` と touched shard の `detail-xx.json` を確認。スクリプト自動判定は禁止）
  4. `python3 tools/manual_guard.py close --session <SESSION_JSON> --audit-report <AUDIT_JSON> --requirement-status PASS --ui-status PASS`
- 1つでも FAIL があれば報告禁止。`needs_manual_fix` 化して再実行する。

## 9. Manual Verification Rule (No Script)
- 検証フェーズで禁止:
  - `python*`、`node*`、`*.py`、`*.js` を使った確認処理
  - 自動巡回・自動判定スクリプト
- 検証フェーズで許可:
  - `firebase` / `curl` / `jq` / `grep` / `sed` / `awk` 等の単発CLIによる公開 JSON 確認
  - Firestore 読み取りによる補助診断
- `firebase` CLI を使う場合、許可される用途は Firestore データ作業または補助診断のみとし、Firebase Hosting 用途では使わないこと。
- live 反映確認の真実源は Firestore ではなく `https://kikidoko.org` 上の公開 JSON とする。
- preview 検証の正規URLは、Cloudflare Pages の deployment details または API が返す branch alias を真実源とする。`https://<sanitized-branch>.kikidoko.pages.dev` を手元で組み立てて確定扱いしてはならない。
- branch alias は lower-case 化や非英数字の `-` 正規化に加えて、Cloudflare 側で truncation や追加整形が入る場合がある前提で扱う。
- Cloudflare Access の login への 302/200 のみでは、正しい branch alias に到達できている証拠にしないこと。必ず Cloudflare Pages 側の `エイリアス` 表示または API 応答と照合する。
- `https://kikidoko.pages.dev` および `https://<hash>.kikidoko.pages.dev` は通常の本番確認先には使わない。
- delivery gate で確認する対象は次の 2 系統とする。
  1. `https://kikidoko.org/data/bootstrap-v1.json`
  2. batch 対象100件が属する全 unique `https://kikidoko.org/data/equipment_detail_shards/detail-xx.json`
- Firestore 読み取りは保存確認や補助診断には使ってよいが、delivery gate の PASS 条件には使わない。
- 次サイクル開始前の固定フロー:
  1. 公開対象ブランチと `main` 反映状態を確認する
  2. `main` 反映前の確認は、対象ブランチが `develop`, `feat/*`, `fix/*`, `chore/*`, `docs/*` のいずれかであれば、Cloudflare Pages の deployment details または API に表示された branch alias URL を確認する
  3. `main` 反映後または一般公開前の確認は、`curl` で `https://kikidoko.org/data/bootstrap-v1.json` を取得し、local `frontend/dist/data/bootstrap-v1.json` の `version/generated_at` と一致することを確認する
  4. batch 対象100件の `doc_id` から local `bootstrap.detail_shard_map` を引き、全 unique touched shard の `detail-xx.json` を確認する
  5. touched shard ごとに、対象 `doc_id` の存在、`manual_content_v1.review.reviewer=codex-manual`、`reviewed_at` 非空、`beginner_guide` 各欄の存在を確認する
  6. `tools/manual_verification_checklist_template.md` に沿って記録保存する
  7. `kikidoko.org` で不一致がある場合、または preview の挙動差分を切り分ける場合のみ `https://kikidoko.pages.dev` または hash 付き preview URL を補助確認する
  8. すべて PASS の場合のみ次サイクル執筆へ進行する

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

## 11. Publication Governance (Mandatory)
- 静的公開物の反映は `firebase deploy` ではなく GitHub 更新で行うこと。
- デフォルト公開フローは `branch -> Cloudflare Pages preview 確認 -> PR -> main 反映 -> Cloudflare Pages 本番` とする。
- Cloudflare Pages の production branch は `main` とする。
- preview 自動配信対象ブランチは `develop`, `feat/*`, `fix/*`, `chore/*`, `docs/*` とする。
- `dependabot/*` は preview 自動配信対象から除外する前提で扱う。
- preview 確認の正規URLは、Cloudflare Pages の deployment details または API に表示された branch alias とし、hash 付き preview URL は deployment 固有の補助確認に限定する。
- branch alias は lower-case 化や非英数字の `-` 正規化に加えて、Cloudflare 側で truncation や追加整形が入る場合がある前提で扱う。
- Cloudflare Access の login への 302/200 のみでは、正しい branch alias に到達できている証拠にしないこと。必ず Cloudflare Pages 側の `エイリアス` 表示または API 応答と照合する。
- preview は Cloudflare Access で保護された内部確認面として扱い、一般公開面は `https://kikidoko.org` のみとする。
- ユーザーが明示的に「main に反映させてください」と指示した場合のみ、PR を省略または main 反映まで進めてよい。
- ファイルまたはコードを変更した作業の完了時には、`main` にプッシュして一般公開するか、開発プレビューへ反映するかを必ずユーザーに確認すること。
- 事前に意向が示されている場合でも、最終反映前に公開先を再確認すること。
- 開発プレビューへ反映する場合は、Cloudflare Pages の deployment details または API で確認した branch alias の確認URLを作業完了メッセージで必ず提示すること。
- 一般公開を選ばず preview 反映で止める場合、`main` 反映・本番公開は行っていないことを明示すること。
- 本番公開確認の真実源は `https://kikidoko.org` とする。
- `https://kikidoko.pages.dev` および hash 付き preview URL は通常の本番確認先にしない。
- Firebase 側で更新してよいのは Firestore データのみとする。
- `firebase deploy`、`firebase hosting:disable`、Firebase Hosting 再有効化、Firebase Hosting ドメイン変更は、ユーザーの明示指示がない限り禁止する。

## 12. Update Info Governance (Mandatory)
- GitHub へ反映する前に、必ずアップデート情報を追加または更新すること。
- source-of-truth は `frontend/update-notes/entries/YYYY/` 配下の Markdown とする。
- 公開用 manifest は `frontend/dist/update-info/index.json` とし、手書きで直接編集してはならない。
- GitHub 反映前に必ず次を通すこと:
  1. `python3 tools/build_update_info_manifest.py`
  2. `python3 tools/verify_update_info_predeploy.py`
  3. `python3 tools/audit_public_tree.py`
- predeploy guard が FAIL の場合、GitHub 反映および公開反映は禁止する。
- `update-history.json` は廃止済み。deploy ログの自動追記運用に戻してはならない。
- アップデート情報ページとホーム画面には、要望投稿・要望一覧を置かないこと。

## 13. Update Info Writing Policy (Mandatory)
- アップデート情報は **原則として簡潔に書く** こと。通常の軽微修正は、ユーザーが分かれば十分な粒度に留める。
- 軽微修正では、実装詳細・内部ファイル名・細かいレイアウト調整の列挙を書かないこと。
- 通常更新の目安:
  - summary は 1 文で要点のみ
  - 本文は `主な更新` の 2〜4 箇条書きに収める
  - ユーザー影響が小さい変更はまとめて記載する
- 次のような **重要な変更** の場合のみ、通常より詳しく書いてよい。
  - 大幅なシステム変更
  - 検索や表示仕様の大きな変更
  - 新規装置の追加やデータ追加
  - 互換性や運用に影響する変更
  - ユーザー影響が大きい不具合修正
- 重要な変更では、背景・変更点・ユーザー影響が分かるように、通常更新より詳しい本文を書いてよい。
- ただし重要変更でも、開発者向けの内部実装メモに寄りすぎないこと。利用者が理解できる説明を優先する。

## 14. Update Info Folder Layout (Mandatory)
- 更新ソース:
  - `frontend/update-notes/entries/YYYY/YYYY-MM-DD-slug.md`
- 更新運用ドキュメント:
  - `frontend/update-notes/README.md`
- 公開 manifest:
  - `frontend/dist/update-info/index.json`
- 生成スクリプト:
  - `tools/build_update_info_manifest.py`
  - `tools/verify_update_info_predeploy.py`

## 15. Public Tree Governance (Mandatory)
- `frontend/dist` は公開物専用とし、運用メモ、README、debug log、plan markdown、`.DS_Store` を置いてはならない。
- `frontend/dist` には `conflicted` を含むファイル名・パスを置いてはならない。競合ファイルを見つけた場合は GitHub 反映前に削除または正規ファイルへ統合すること。
- source は `frontend/content/**`、public は `frontend/dist/**` に分離すること。
- patch は `frontend/dist/patches/<function-name>.css/js` に統一し、日付だけの patch ファイル名を新規作成してはならない。
- ブログ記事の source markdown は `frontend/content/blog/articles/*.md` に置き、`frontend/dist` に markdown を公開してはならない。
- `frontend/dist/blog/articles.json` は生成物とし、手で直接編集してはならない。
- `frontend/dist/blog/articles.json` は正規 1 ファイルのみを許可する。`articles [conflicted].json` 等の派生ファイルを残してはならない。
- GitHub 反映前に必ず `python3 tools/build_blog_articles_manifest.py` と `python3 tools/audit_public_tree.py` を通すこと。
- public tree audit が FAIL の場合、GitHub 反映および公開反映は禁止する。
- public root 直下に新しいファイルを追加する場合は、現行 runtime/tool がその直パスを参照していることを確認すること。そうでなければ `data/`, `patches/`, `brand/`, `update-info/` の既存責務ディレクトリへ入れること。
