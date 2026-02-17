# Firebase Hosting 更新 Runbook（kikidoko）

最終更新日: 2026-02-15  
対象: `kikidoko` プロジェクトの Frontend 配信（`kikidoko.web.app` / カスタムドメイン）

## 1. 目的

- React フロントを Firebase Hosting に配信する。
- `/blog/*` は `kikidoko-blog.student-subscription.com` へ 301 リダイレクトする。
- 初回表示高速化のため snapshot（`equipment_snapshot.json.gz`）を同梱する。

## 2. 前提

- 作業ディレクトリ: `/Users/niigatadaigakukenkyuuyou/Downloads/kikidoko`
- Firebase プロジェクト: `kikidoko`
- 必要ツール:
  - Node.js 20.19+ または 22.12+
  - Firebase CLI
  - Python 3.11 + `crawler/.venv`
- 認証ファイル:
  - `/Users/niigatadaigakukenkyuuyou/Downloads/kikidoko/kikidoko-11493efc7f47.json`

## 3. リリース手順（毎回同じ）

### Step 0: 事前確認

```bash
cd /Users/niigatadaigakukenkyuuyou/Downloads/kikidoko
firebase projects:list
```

- `kikidoko` が見えることを確認。

### Step 1: snapshot 生成（必須）

```bash
cd /Users/niigatadaigakukenkyuuyou/Downloads/kikidoko
PYTHONPATH=crawler/src \
GOOGLE_APPLICATION_CREDENTIALS=/Users/niigatadaigakukenkyuuyou/Downloads/kikidoko/kikidoko-11493efc7f47.json \
./crawler/.venv/bin/python -m kikidoko_crawler.snapshot_export \
  --project-id kikidoko \
  --output frontend/public/equipment_snapshot.json.gz
```

```bash
ls -lh frontend/public/equipment_snapshot.json.gz
```

- `frontend/public/equipment_snapshot.json.gz` が存在し、サイズが 0 でないこと。
- 新形式 snapshot（軽量）であることを確認:

```bash
python3 - <<'PY'
import gzip, json
with gzip.open('frontend/public/equipment_snapshot.json.gz', 'rt', encoding='utf-8') as f:
    payload = json.load(f)
print('schema_version=', payload.get('schema_version'))
print('sorted_by=', payload.get('sorted_by'))
print('count=', payload.get('count'))
PY
```

- このファイルは Git コミットしない。

### Step 2: フロントの lint/build

```bash
cd /Users/niigatadaigakukenkyuuyou/Downloads/kikidoko/frontend
npm run lint
npm run build
```

### Step 3: preview デプロイ

```bash
cd /Users/niigatadaigakukenkyuuyou/Downloads/kikidoko
firebase hosting:channel:deploy preprod --project kikidoko
```

返却された preview URL を `PREVIEW_URL` として、以下を検証:

```bash
curl -L -s -o /tmp/kikidoko_preview_root.html -w '%{http_code}\n' "$PREVIEW_URL/"
rg -n 'id="root"' /tmp/kikidoko_preview_root.html

curl -I -s "$PREVIEW_URL/equipment_snapshot.json.gz" | sed -n '1,20p'
curl -L -s "$PREVIEW_URL/equipment_snapshot.json.gz" | head -c 64 | xxd

curl -I -s "$PREVIEW_URL/blog/" | sed -n '1,20p'
curl -I -s "$PREVIEW_URL/blog/guide/research-equipment-sharing-basics/" | sed -n '1,25p'

curl -I -s "$PREVIEW_URL/terms.html" | sed -n '1,20p'
curl -I -s "$PREVIEW_URL/privacy-policy.html" | sed -n '1,20p'
```

合格条件:
- `/` が `200` かつ `id="root"` を含む。
- `/equipment_snapshot.json.gz` が `200`、HTML ではない。
- `/blog/*` が 301 で `https://kikidoko-blog.student-subscription.com/*` へ遷移。
- `/terms.html` と `/privacy-policy.html` が `200`。

### Step 4: 本番デプロイ

```bash
cd /Users/niigatadaigakukenkyuuyou/Downloads/kikidoko
firebase deploy --only hosting --project kikidoko
```

### Step 5: 本番スモークチェック

```bash
curl -L -s -o /tmp/kikidoko_prod_root.html -w '%{http_code}\n' https://kikidoko.web.app/
rg -n 'id="root"' /tmp/kikidoko_prod_root.html

curl -I -s https://kikidoko.web.app/equipment_snapshot.json.gz | sed -n '1,20p'
curl -I -s https://kikidoko.web.app/blog/ | sed -n '1,20p'
curl -I -s https://kikidoko.web.app/blog/guide/research-equipment-sharing-basics/ | sed -n '1,25p'
curl -I -s https://kikidoko.web.app/terms.html | sed -n '1,20p'
curl -I -s https://kikidoko.web.app/privacy-policy.html | sed -n '1,20p'
```

ブラウザ確認（手動）:
- `https://kikidoko.web.app/?debugReads=1` をハードリロードし、`snapshot (...) docs` 表示を確認。
- 初回表示時に致命的エラー（赤エラー）がないこと。

## 4. ロールバック

優先度順:

1. Firebase Console の Hosting release history から直前リリースへ rollback。
2. CLI で clone/rollback（必要時のみ）。
3. 重大障害時は DNS を旧配信先へ戻す（独自ドメイン運用時）。

## 5. 禁止事項

- `frontend/public/equipment_snapshot.json.gz` を Git へコミットしない。
- preview 未検証のまま本番へ出さない。
- `/blog/*` の 301 設定を削除しない。
- 変更内容を runbook に反映せず、暗黙運用を増やさない。

## 6. 参考ファイル

- `/Users/niigatadaigakukenkyuuyou/Downloads/kikidoko/firebase.json`
- `/Users/niigatadaigakukenkyuuyou/Downloads/kikidoko/.firebaserc`
- `/Users/niigatadaigakukenkyuuyou/Downloads/kikidoko/crawler/src/kikidoko_crawler/snapshot_export.py`
