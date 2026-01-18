# Crawler

This package contains the scraping pipeline that collects equipment data and writes it to Firestore.

## Local setup

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Run (dry)

```sh
kikidoko-crawl --source university --dry-run
```

## Environment

- `KIKIDOKO_PROJECT_ID`: Firestore project id
- `GOOGLE_APPLICATION_CREDENTIALS`: path to the service account JSON
- `KIKIDOKO_DRY_RUN`: set to `1` to skip Firestore writes
- `KIKIDOKO_OUTPUT_PATH`: JSONL output path for dry runs
