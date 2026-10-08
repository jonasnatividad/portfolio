# File Drop to BigQuery

An event-driven pipeline for the most common small-company data source: CSV exports.
A CRM (or a person) drops daily CSV files into a Cloud Storage bucket; a Cloud Run
service loads each file into BigQuery as soon as it lands; three layers of SQL views
turn the raw rows into trusted reporting tables; and a scheduled service publishes the
results to a Google Sheet the team already uses.

The example is a fictional B2B SaaS sales team with two exports, `companies` and
`deals`. The data is synthetic (`scripts/generate_sample_data.py`) and deliberately a
little messy.

## Flow

```
CRM export (CSV)
   │
   ▼
gs://your-drop-bucket/incoming/{companies|deals}/*.csv
   │  Eventarc: object finalized
   ▼
Cloud Run: csv-loader ───────────────► sales_raw.companies / sales_raw.deals
   │  header check, load as STRING,          (append-only, every file kept)
   │  load log, move file to processed/ or rejected/
   ▼
sales_clean.*   typed, trimmed, deduplicated, latest version per id
   ▼
sales_live.*    business logic: stage order, win probability, weighted pipeline,
   │            overdue flag, days in stage, data quality checks
   ▼
sales_prod.*    stable reporting contract: pipeline by stage, rep scorecard, forecast
   │
   │  Cloud Scheduler 07:00 America/New_York
   ▼
Cloud Run: sales-sheet-refresh ─────► Google Sheet (one tab per prod view + Status)
```

## Design choices

**Raw is append-only and untyped.** Every column is loaded as STRING with the source
file, file date and load time. A bad date or a `$1,200.00` amount never fails a load,
and any past file can be replayed or audited from the raw table.

**Three view layers, each with one job.**
- *clean*: one row per entity, safe casts (`SAFE_CAST`, `SAFE.PARSE_DATE`), trimming,
  standardized casing, and "latest version wins" deduplication across daily snapshots.
  `deal_stage_history` also recovers when each deal entered each stage, which the CRM
  export does not provide.
- *live*: business definitions in one place (stage order and win probability, weighted
  pipeline, overdue, days in stage) and a `data_quality` view.
- *prod*: the contract that sheets and dashboards depend on. Prod views read only from
  live views, and their columns change only on purpose.

  Because they are views, the layers never go stale and need no orchestration. If query
  cost grows, any layer can become a scheduled table or materialized view without
  changing the layers above it.

**Idempotent loading.** The loader records each object generation in `_load_log` and
skips repeats, so Eventarc's at-least-once delivery cannot double-load a file. Files
are moved to `processed/` or `rejected/` (with the reason logged), leaving `incoming/`
as a clear to-do list.

**Fail closed on publish.** The sheet refresh checks `sales_live.data_quality` first.
Blocking problems (deals without a company, an unknown stage, no new file in 36 hours)
stop the publish with HTTP 409; warnings (missing amounts) are published on the Status
tab.

## Files

```
file_drop_to_bigquery/
├── sample_data/                    synthetic CRM exports (2 days of deals)
├── scripts/
│   ├── generate_sample_data.py     rebuild the sample files
│   └── deploy_views.sh             create datasets, raw tables and views in order
├── sql/
│   ├── 00_setup.sql                datasets, raw tables, load log
│   ├── clean/                      companies, deals, deal_stage_history
│   ├── live/                       deal_pipeline, data_quality
│   ├── prod/                       pipeline_by_stage, rep_scorecard, forecast_by_month
│   └── checks/assertions.sql       blocking checks as ASSERTs, for a scheduled query with failure emails
├── services/
│   ├── loader/                     Cloud Run: GCS -> BigQuery raw
│   └── sheet_refresh/              Cloud Run: prod views -> Google Sheet (gspread)
├── tests/test_offline.py           routing, header checks, event handling, SQL parsing (no cloud access)
└── SCHEDULING.md                   Eventarc trigger and Cloud Scheduler job
```

## Setup

```bash
PROJECT=your-gcp-project
REGION=us-central1
BUCKET=your-drop-bucket

# 1. Bucket, datasets, tables, views
gcloud storage buckets create gs://$BUCKET --location US --project $PROJECT
PROJECT=$PROJECT ./scripts/deploy_views.sh

# 2. Service accounts
gcloud iam service-accounts create csv-loader --project $PROJECT
gcloud iam service-accounts create sheet-refresh --project $PROJECT
for SA in csv-loader sheet-refresh; do
  gcloud projects add-iam-policy-binding $PROJECT \
    --member serviceAccount:$SA@$PROJECT.iam.gserviceaccount.com --role roles/bigquery.jobUser
done
# csv-loader: write sales_raw, read/move objects in the bucket
# sheet-refresh: read sales_live, sales_prod and sales_raw
# (grant roles/bigquery.dataEditor / dataViewer on those datasets, and
#  roles/storage.objectAdmin on the bucket for csv-loader)

# 3. Build and deploy both services
for SVC in loader:csv-loader sheet_refresh:sales-sheet-refresh; do
  DIR=${SVC%%:*}; NAME=${SVC##*:}
  gcloud builds submit services/$DIR --project $PROJECT \
    --tag $REGION-docker.pkg.dev/$PROJECT/pipelines/$NAME:latest
  gcloud run services replace services/$DIR/service.yaml --region $REGION --project $PROJECT
done

# 4. Share the Google Sheet with sheet-refresh@$PROJECT.iam.gserviceaccount.com (Editor)
#    and put its id in services/sheet_refresh/service.yaml (SHEET_ID).

# 5. Triggers: see SCHEDULING.md
```

## Try it with the sample data

```bash
gcloud storage cp sample_data/companies_2026-09-30.csv gs://$BUCKET/incoming/companies/
gcloud storage cp sample_data/deals_2026-09-30.csv     gs://$BUCKET/incoming/deals/
gcloud storage cp sample_data/deals_2026-10-01.csv     gs://$BUCKET/incoming/deals/
```

Then query `sales_prod.pipeline_by_stage`, or call the refresh with
`?dry_run=true` to see row counts without touching the sheet. (The `stale_data` check
blocks publishing if the newest file is more than 36 hours old, which will be the case
for the sample files after a day or two; that is the check doing its job.)

## Checks and tests

```bash
pip install -r services/loader/requirements.txt sqlglot
python3 -m unittest discover -s tests
```

The tests need no Google Cloud credentials: the loader creates its BigQuery and
Storage clients on first use, so routing, header checks and event handling run
offline, and every SQL file is parsed with sqlglot (BigQuery dialect).

In production, `sql/checks/assertions.sql` runs as a daily BigQuery scheduled
query with failure emails on. It fails if any blocking data quality check fails or
if a clean table holds more than one row per id, so a broken export is noticed even
on days nobody opens the sheet.

## Adapting it to another dataset

Three places carry the dataset-specific parts: `EXPECTED_COLUMNS` in the loader
(one entry per source folder), `sql/00_setup.sql` (one raw table per source, all
STRING), and the view layers. The loader, load log, file moves and the data quality
gate stay as they are. For a new source, add its folder name and columns, add its
raw table, write its clean view with the same pattern (safe casts, newest version
wins), and expose what the business needs in prod.

## Swapping Google Sheets for another destination

`write_tab` is the only Sheets-specific function. Replacing it with a call to another
tool's API (for example a Grist or Airtable table) leaves the rest of the service as is.
