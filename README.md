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
kikidoko-crawl --source nagoya --dry-run
kikidoko-crawl --source niigata --dry-run
kikidoko-crawl --source kyoto --dry-run
kikidoko-crawl --source tohoku --dry-run
kikidoko-crawl --source utokyo --dry-run
kikidoko-crawl --source tsukuba --dry-run
kikidoko-crawl --source tmd --dry-run
```

## Environment

- `KIKIDOKO_PROJECT_ID`: Firestore project id
- `GOOGLE_APPLICATION_CREDENTIALS`: path to the service account JSON
- `KIKIDOKO_DRY_RUN`: set to `1` to skip Firestore writes

## Source policy

- Prefer HTML/CSV/JSON endpoints.
- Avoid parsing PDFs; if a source is PDF-only, log it and look for a non-PDF alternative.
- Skip equipment lists that require login to view.
