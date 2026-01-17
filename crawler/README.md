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
kikidoko-crawl --source eqnet --dry-run
```

## Eqnet configuration

The eqnet crawler expects a list endpoint (HTML or JSON). Provide either:

- `EQNET_LIST_URL` (preferred)
- or `--list-url` CLI flag

If list entries do not include detail URLs, also provide:

- `EQNET_DETAIL_URL_TEMPLATE` (e.g. `https://example.com/detail?id={id}`)
- or `--detail-url-template` CLI flag

## Environment

- `KIKIDOKO_PROJECT_ID`: Firestore project id
- `GOOGLE_APPLICATION_CREDENTIALS`: path to the service account JSON
- `KIKIDOKO_DRY_RUN`: set to `1` to skip Firestore writes
- `EQNET_LIST_URL`: list endpoint URL for eqnet (HTML or JSON)
- `EQNET_DETAIL_URL_TEMPLATE`: detail page URL template (use `{id}`)
- `KIKIDOKO_OUTPUT_PATH`: JSONL output path for dry runs
