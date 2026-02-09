# Kikidoko 半年更新運用手順書

本手順は、半年ごと（推奨: 2月・8月）にEQNETおよび既存スクレイピング結果を再同期するための運用手順です。

## 1. 事前準備

1. 作業ディレクトリへ移動
   - `cd /Users/niigatadaigakukenkyuuyou/Downloads/kikidoko`
2. Python仮想環境を準備（未作成時）
   - `python3 -m venv crawler/.venv`
   - `crawler/.venv/bin/pip install -e crawler`
3. 認証情報を設定
   - `export GOOGLE_APPLICATION_CREDENTIALS=/Users/niigatadaigakukenkyuuyou/Downloads/kikidoko/kikidoko-11493efc7f47.json`
   - `export KIKIDOKO_PROJECT_ID=kikidoko`

## 2. 都道府県欠損の監査（dry-run）

1. EQNET機関→都道府県辞書を更新し、欠損監査CSVを作成
   - `./crawler/.venv/bin/python -m kikidoko_crawler.eqnet_prefecture_sync --project-id kikidoko --dry-run`
2. 生成ファイルを確認
   - `crawler/eqnet_org_prefecture_map.csv`
   - `crawler/prefecture_gap_audit.csv`
   - `crawler/prefecture_gap_fix_preview.csv`
3. `prefecture_gap_audit.csv` の `status` が以下の件数を確認
   - `update_candidate`
   - `unresolved_org_not_mapped`
   - `unresolved_no_org_name`

## 3. 未取込機関の差分投入

1. dry-runで未取込機関リストを作成
   - `./crawler/.venv/bin/python -m kikidoko_crawler.eqnet_org_gap_fill --project-id kikidoko --dry-run`
2. `crawler/eqnet_missing_orgs.csv` を確認
3. 未取込がある場合のみ本実行
   - `./crawler/.venv/bin/python -m kikidoko_crawler.eqnet_org_gap_fill --project-id kikidoko`

## 4. 都道府県補完の本実行

1. 本実行（`prefecture` が空のEQNET由来データを補完）
   - `./crawler/.venv/bin/python -m kikidoko_crawler.eqnet_prefecture_sync --project-id kikidoko`
2. 再度dry-runを実施し、`update_candidate` が大幅減少したことを確認
   - `./crawler/.venv/bin/python -m kikidoko_crawler.eqnet_prefecture_sync --project-id kikidoko --dry-run`

## 5. EQNETカテゴリ同期

1. dry-runでカテゴリ更新対象を確認
   - `./crawler/.venv/bin/python -m kikidoko_crawler.eqnet_category_sync --project-id kikidoko --dry-run`
2. 本実行
   - `./crawler/.venv/bin/python -m kikidoko_crawler.eqnet_category_sync --project-id kikidoko`

## 6. 手作業用途説明の反映

1. 差分確認
   - `wc -l crawler/manual_usage_overrides.json crawler/manual_usage_done.csv`
2. Firestore反映
   - `./crawler/.venv/bin/python -m kikidoko_crawler.apply_manual_usage --project-id kikidoko --input crawler/manual_usage_overrides.json`

## 7. 集計再生成

1. 検索・地図用の都道府県サマリーを再生成
   - `./crawler/.venv/bin/python -m kikidoko_crawler.backfill --project-id kikidoko --write-summary`
2. フロント表示の確認項目
   - 欠損だった都道府県が地図でクリック可能になっている
   - 「該当なし」が不正表示されない
   - 都道府県別件数と検索結果の整合が取れている

## 8. ロールバック方針

1. CSV監査ファイルを作成済みであることを前提に、問題発生時は影響範囲を特定
   - `prefecture_gap_fix_preview.csv`（都道府県補完対象）
   - `eqnet_category_update_preview.csv`（カテゴリ更新対象）
2. 反映時刻で切って再同期する場合
   - `prefecture_synced_at` / `eqnet_category_synced_at` で抽出
3. 大規模不整合時は以下順序で復旧
   - 直近バックアップ復元
   - `eqnet_org_gap_fill` 再実行
   - `eqnet_prefecture_sync` 再実行
   - `eqnet_category_sync` 再実行
   - `backfill --write-summary` 再実行

## 9. 運用ログの記録

毎回、以下を `dev-log` に残してください。

1. 実行日時（JST/UTC）
2. 実行コマンド一覧
3. 更新件数（都道府県補完、カテゴリ、用途説明）
4. unresolved件数と対象機関
5. フロント確認結果
