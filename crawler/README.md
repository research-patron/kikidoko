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
kikidoko-crawl --source hokudai --dry-run
kikidoko-crawl --source aist --dry-run
kikidoko-crawl --source kyushu --dry-run
kikidoko-crawl --source riken --dry-run
kikidoko-crawl --source ims --dry-run
kikidoko-crawl --source nims --dry-run
kikidoko-crawl --source tohoku --dry-run
kikidoko-crawl --source utokyo --dry-run
kikidoko-crawl --source tsukuba --dry-run
kikidoko-crawl --source tmd --dry-run
kikidoko-crawl --source all --dry-run
```

## Environment

- `KIKIDOKO_PROJECT_ID`: Firestore project id
- `GOOGLE_APPLICATION_CREDENTIALS`: path to the service account JSON
- `KIKIDOKO_DRY_RUN`: set to `1` to skip Firestore writes
- `KIKIDOKO_OUTPUT_PATH`: JSONL output path for dry runs

## Source policy

- Prefer HTML/CSV/JSON endpoints.
- Avoid parsing PDFs; if a source is PDF-only, log it and look for a non-PDF alternative.
- Skip equipment lists that require login to view.
