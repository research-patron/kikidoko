# kikidoko

Research equipment cross-search service for public institutions in Japan.

## Structure

- `frontend/`: React (Vite) UI
- `crawler/`: Python crawler that writes equipment data to Firestore

## Requirements

- Node.js 20+
- Python 3.11+

## Frontend

```sh
cd frontend
npm install
npm run dev
```

## Crawler

```sh
cd crawler
python -m venv .venv
source .venv/bin/activate
pip install -e .

kikidoko-crawl --source hokudai --dry-run
kikidoko-crawl --source riken --dry-run
kikidoko-crawl --source ims --dry-run
kikidoko-crawl --source nims --dry-run
kikidoko-crawl --source chiba --dry-run
kikidoko-crawl --source ehime --dry-run
kikidoko-crawl --source fukui --dry-run
kikidoko-crawl --source gifu --dry-run
kikidoko-crawl --source gunma --dry-run
kikidoko-crawl --source hiroshima --dry-run
kikidoko-crawl --source ibaraki --dry-run
kikidoko-crawl --source nagoya --dry-run
kikidoko-crawl --source niigata --dry-run
kikidoko-crawl --source kyoto --dry-run
kikidoko-crawl --source iwate --dry-run
kikidoko-crawl --source tohoku --dry-run
kikidoko-crawl --source utokyo --dry-run
kikidoko-crawl --source tsukuba --dry-run
kikidoko-crawl --source tmd --dry-run
kikidoko-crawl --source jaist --dry-run
kikidoko-crawl --source kek --dry-run
kikidoko-crawl --source kagoshima --dry-run
kikidoko-crawl --source kanazawa --dry-run
kikidoko-crawl --source kitami --dry-run
kikidoko-crawl --source kobe --dry-run
kikidoko-crawl --source kumamoto --dry-run
kikidoko-crawl --source kyutech --dry-run
kikidoko-crawl --source mie --dry-run
kikidoko-crawl --source miyazaki --dry-run
kikidoko-crawl --source muroran --dry-run
kikidoko-crawl --source nagaoka --dry-run
kikidoko-crawl --source nagasaki --dry-run
kikidoko-crawl --source naist --dry-run
kikidoko-crawl --source nitech --dry-run
kikidoko-crawl --source obihiro --dry-run
kikidoko-crawl --source ochanomizu --dry-run
kikidoko-crawl --source oita --dry-run
kikidoko-crawl --source saga --dry-run
kikidoko-crawl --source okayama --dry-run
kikidoko-crawl --source oist --dry-run
kikidoko-crawl --source osaka --dry-run
```

## Environment

- `KIKIDOKO_PROJECT_ID`: Firestore project id
- `GOOGLE_APPLICATION_CREDENTIALS`: path to the service account JSON
- `KIKIDOKO_DRY_RUN`: set to `1` to skip Firestore writes

## Source policy

- Prefer HTML/CSV/JSON endpoints.
- Avoid parsing PDFs; if a source is PDF-only, log it and look for a non-PDF alternative.
- Skip equipment lists that require login to view.
