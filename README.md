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

kikidoko-crawl --source eqnet --dry-run
```

## Environment

- `KIKIDOKO_PROJECT_ID`: Firestore project id
- `GOOGLE_APPLICATION_CREDENTIALS`: path to the service account JSON
- `KIKIDOKO_DRY_RUN`: set to `1` to skip Firestore writes
