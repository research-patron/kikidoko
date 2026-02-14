# Kikidoko 半年更新運用手順書

本手順は、半年ごと（推奨: 2月・8月）に EQNET と各機関ページを再同期するための運用手順です。

## 1. 事前準備

1. 作業ディレクトリへ移動
   - `cd /Users/niigatadaigakukenkyuuyou/Downloads/kikidoko`
2. Python仮想環境を準備（未作成時）
   - `python3 -m venv crawler/.venv`
   - `crawler/.venv/bin/pip install -e crawler`
3. 認証情報を設定
   - `export GOOGLE_APPLICATION_CREDENTIALS=/Users/niigatadaigakukenkyuuyou/Downloads/kikidoko/kikidoko-11493efc7f47.json`
   - `export KIKIDOKO_PROJECT_ID=kikidoko`

## 2. eqnet外候補の更新（先頭で実施）

1. Firestore読取なしで候補を再抽出
   - `./crawler/.venv/bin/python -m kikidoko_crawler.source_registry_sync --dry-run --project-id '' --registry crawler/config/source_registry_low_count.json --preview-out /tmp/source_registry_sync_preview.csv`
2. 候補/バックログCSVを生成
   - `./crawler/.venv/bin/python -m kikidoko_crawler.source_registry_candidate_refresh --preview-csv /tmp/source_registry_sync_preview.csv --registry crawler/config/source_registry_low_count.json --candidate-out crawler/source_registry_candidate_refresh.csv --backlog-out crawler/source_registry_query_only_backlog.csv`
3. 生成ファイルを確認
   - `crawler/source_registry_candidate_refresh.csv`（`sync_now / implement_source / verify_url`）
   - `crawler/source_registry_query_only_backlog.csv`（query_only機関のURL/取得方式管理）
4. `action=sync_now` を同期対象、`action=implement_source` を次回実装対象として振り分ける

## 3. 低件数都道府県の監査（重点）

1. 2桁都道府県・1桁機関の監査を実行
   - `./crawler/.venv/bin/python -m kikidoko_crawler.low_count_prefecture_audit --project-id kikidoko --dry-run`
2. 生成ファイルを確認
   - `crawler/low_count_prefecture_report.csv`
   - `crawler/low_count_org_report.csv`
   - `crawler/low_count_org_priority.csv`
3. メモを確認
   - `memo/YYYY-MM-DD_低件数都道府県再分析.md`

## 4. 低件数機関の補完スクレイピング（registry）

1. 優先CSVを確認し、必要な機関を `crawler/config/source_registry_low_count.json` に反映
2. dry-run 実行
   - `./crawler/.venv/bin/python -m kikidoko_crawler.source_registry_sync --project-id kikidoko --dry-run --priority-csv crawler/low_count_org_priority.csv`
3. プレビュー確認
   - `crawler/source_registry_sync_preview.csv`
4. 本実行
   - `./crawler/.venv/bin/python -m kikidoko_crawler.source_registry_sync --project-id kikidoko --priority-csv crawler/low_count_org_priority.csv`

## 5. 都道府県欠損の監査（dry-run）

1. EQNET機関→都道府県辞書を更新し、欠損監査CSVを作成
   - `./crawler/.venv/bin/python -m kikidoko_crawler.eqnet_prefecture_sync --project-id kikidoko --dry-run`
2. 生成ファイルを確認
   - `crawler/eqnet_org_prefecture_map.csv`
   - `crawler/prefecture_gap_audit.csv`
   - `crawler/prefecture_gap_fix_preview.csv`
3. `prefecture_gap_audit.csv` の `status` 件数を確認
   - `update_candidate`
   - `unresolved_org_not_mapped`
   - `unresolved_no_org_name`

## 6. 未取込機関の差分投入

1. dry-run で未取込機関リスト作成
   - `./crawler/.venv/bin/python -m kikidoko_crawler.eqnet_org_gap_fill --project-id kikidoko --dry-run`
2. `crawler/eqnet_missing_orgs.csv` を確認
3. 未取込がある場合のみ本実行
   - `./crawler/.venv/bin/python -m kikidoko_crawler.eqnet_org_gap_fill --project-id kikidoko`

## 7. 都道府県補完の本実行

1. 本実行（`prefecture` が空の EQNET 由来データを補完）
   - `./crawler/.venv/bin/python -m kikidoko_crawler.eqnet_prefecture_sync --project-id kikidoko`
2. 再度 dry-run を実施し、`update_candidate` が減少したことを確認
   - `./crawler/.venv/bin/python -m kikidoko_crawler.eqnet_prefecture_sync --project-id kikidoko --dry-run`

## 8. EQNETカテゴリ同期

1. dry-run でカテゴリ更新対象を確認
   - `./crawler/.venv/bin/python -m kikidoko_crawler.eqnet_category_sync --project-id kikidoko --dry-run`
2. 本実行
   - `./crawler/.venv/bin/python -m kikidoko_crawler.eqnet_category_sync --project-id kikidoko`

## 9. 関連論文（DOI）再検証

1. 「準備中」対象を監査CSVへ出力
   - `./crawler/.venv/bin/python -m kikidoko_crawler.papers_audit --project-id kikidoko --output crawler/papers_pending_audit.csv`
2. dry-run で再検索の結果を確認
   - `./crawler/.venv/bin/python -m kikidoko_crawler.papers_backfill --project-id kikidoko --only-pending --input-csv crawler/papers_pending_audit.csv --max-queries-per-doc 3 --mark-verified-no-results --dry-run`
3. 本実行
   - `./crawler/.venv/bin/python -m kikidoko_crawler.papers_backfill --project-id kikidoko --only-pending --input-csv crawler/papers_pending_audit.csv --max-queries-per-doc 3 --mark-verified-no-results`
4. 再監査で残件確認
   - `./crawler/.venv/bin/python -m kikidoko_crawler.papers_audit --project-id kikidoko --output crawler/papers_pending_audit.csv`
5. 生成ファイル確認
   - `crawler/papers_pending_audit.csv`
   - `crawler/papers_recheck_result.csv`

## 9.1 no_results_verified の厳密再検証（Scopus）

1. no_results_verified 対象を抽出
   - `./crawler/.venv/bin/python -m kikidoko_crawler.papers_audit --project-id kikidoko --status no_results_verified --output crawler/papers_no_results_verified_376.csv`
2. 厳密再検証（dry-run）
   - `./crawler/.venv/bin/python -m kikidoko_crawler.papers_strict_recheck --project-id kikidoko --input-csv crawler/papers_no_results_verified_376.csv --dry-run --output-candidates crawler/papers_strict_candidates.csv --output-manual-review crawler/papers_strict_manual_review.csv --output-result crawler/papers_strict_apply_result.csv`
3. 必要に応じて `crawler/config/papers_doc_query_overrides.csv` を更新し再dry-run
4. 本反映（手動判定CSVを使う場合は `--manual-review-csv` を追加）
   - `./crawler/.venv/bin/python -m kikidoko_crawler.papers_strict_recheck --project-id kikidoko --input-csv crawler/papers_no_results_verified_376.csv --apply --manual-review-csv crawler/papers_strict_manual_review.csv --output-candidates crawler/papers_strict_candidates.csv --output-manual-review crawler/papers_strict_manual_review.csv --output-result crawler/papers_strict_apply_result.csv`
5. 出力確認
   - `crawler/papers_no_results_verified_376.csv`
   - `crawler/papers_strict_candidates.csv`
   - `crawler/papers_strict_manual_review.csv`
   - `crawler/papers_strict_apply_result.csv`

## 10. 手作業用途説明の反映

1. 差分確認
   - `wc -l crawler/manual_usage_overrides.json crawler/manual_usage_done.csv`
2. Firestore反映
   - `./crawler/.venv/bin/python -m kikidoko_crawler.apply_manual_usage --project-id kikidoko --input crawler/manual_usage_overrides.json`

## 11. 集計再生成

1. 検索・地図用の都道府県サマリーを再生成
   - `./crawler/.venv/bin/python -m kikidoko_crawler.backfill --project-id kikidoko --write-summary`
2. フロント表示確認
   - 欠損都道府県が地図でクリック可能
   - 「該当なし」が不正表示されない
   - 都道府県別件数と検索結果が整合

## 12. ロールバック方針

1. 監査CSVで影響範囲を特定
   - `prefecture_gap_fix_preview.csv`（都道府県補完対象）
   - `eqnet_category_update_preview.csv`（カテゴリ更新対象）
   - `source_registry_sync_preview.csv`（低件数補完対象）
   - `source_registry_candidate_refresh.csv`（候補振り分け結果）
2. 反映時刻で抽出
   - `prefecture_synced_at` / `eqnet_category_synced_at` / `source_registry_synced_at`
3. 復旧順序
   - 直近バックアップ復元
   - `source_registry_sync` 再実行
   - `eqnet_org_gap_fill` 再実行
   - `eqnet_prefecture_sync` 再実行
   - `eqnet_category_sync` 再実行
   - `backfill --write-summary` 再実行

## 13. 運用ログの記録

毎回、以下を `dev-log` に記録してください。

1. 実行日時（JST/UTC）
2. 実行コマンド一覧
3. 更新件数（低件数補完、都道府県補完、カテゴリ、用途説明）
4. unresolved 件数と対象機関
5. フロント確認結果
