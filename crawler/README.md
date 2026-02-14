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
kikidoko-crawl --source titech --dry-run
kikidoko-crawl --source tuat --dry-run
kikidoko-crawl --source tottori --dry-run
kikidoko-crawl --source toyohashi --dry-run
kikidoko-crawl --source uec --dry-run
kikidoko-crawl --source utsunomiya --dry-run
kikidoko-crawl --source yamaguchi --dry-run
kikidoko-crawl --source yamanashi --dry-run
kikidoko-crawl --source ynu --dry-run
kikidoko-crawl --source jaist --dry-run
kikidoko-crawl --source kek --dry-run
kikidoko-crawl --source kagoshima --dry-run
kikidoko-crawl --source kagawa --dry-run
kikidoko-crawl --source kochi --dry-run
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
kikidoko-crawl --source shimane --dry-run
kikidoko-crawl --source shinshu --dry-run
kikidoko-crawl --source tokushima --dry-run
kikidoko-crawl --source okayama --dry-run
kikidoko-crawl --source oist --dry-run
kikidoko-crawl --source osaka --dry-run
kikidoko-crawl --source ryukyu --dry-run
kikidoko-crawl --source all --dry-run
```

## Environment

- `KIKIDOKO_PROJECT_ID`: Firestore project id
- `GOOGLE_APPLICATION_CREDENTIALS`: path to the service account JSON
- `KIKIDOKO_DRY_RUN`: set to `1` to skip Firestore writes
- `KIKIDOKO_OUTPUT_PATH`: JSONL output path for dry runs

## EQNET link backfill

```sh
kikidoko-eqnet-backfill --project-id <your-project-id> --dry-run --limit 50
kikidoko-eqnet-backfill --project-id <your-project-id> --batch-size 200
```

## UI stats backfill

```sh
kikidoko-backfill \
  --project-id <your-project-id> \
  --write-summary \
  --write-ui-filters \
  --write-prefecture-orgs \
  --write-data-version
```

## Map org release checks

Run this before deploying frontend changes that depend on `stats/prefecture_orgs`.

1. Regenerate stats:

```sh
kikidoko-backfill \
  --project-id <your-project-id> \
  --write-summary \
  --write-ui-filters \
  --write-prefecture-orgs \
  --write-data-version
```

2. Verify Firestore documents:
- `stats/prefecture_orgs/prefectures/*` has 47 prefecture docs.
- `stats/data_version` has a fresh `updated_at`.

3. If snapshot mode is used, verify the snapshot file exists:

```sh
ls -lh frontend/public/equipment_snapshot.json.gz
```

## Static snapshot export

```sh
kikidoko-export-snapshot --project-id <your-project-id> --output frontend/public/equipment_snapshot.json.gz
```

## Source policy

- Prefer HTML/CSV/JSON endpoints.
- Avoid parsing PDFs; if a source is PDF-only, log it and look for a non-PDF alternative.
- Skip equipment lists that require login to view.
