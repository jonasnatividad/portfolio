# Warehouse to Postgres Sync

A small Cloud Run service that copies selected BigQuery tables into a Postgres database
(Supabase, Cloud SQL, or any Postgres) on a schedule, incrementally. A typical use:
the warehouse is the source of truth, but an internal app or API needs fast, row-level
reads that BigQuery is not built for.

The example source is BigQuery's public `bigquery-public-data.thelook_ecommerce`
(a synthetic online retailer), so it runs without any private data.

## How it works

```
Cloud Scheduler (every 15 min)
        │  POST /sync  (OIDC auth)
        ▼
Cloud Run: warehouse-to-postgres-sync
        │ 1. read last watermark per table  ◄── Postgres retail.sync_state
        │ 2. SELECT rows WHERE watermark > last - lookback ── BigQuery
        │ 3. batch upsert (ON CONFLICT DO UPDATE)  ──► Postgres retail.<table>
        │ 4. save new watermark
```

- **Config, not code.** `tables.yml` lists each table, its primary key, the columns to
  copy and a mode: `incremental` (with a `watermark_sql` expression) or `full`.
- **Watermark that sees updates.** For orders the watermark is the latest of
  created/shipped/delivered/returned, so a status change re-syncs the row, not just
  new rows.
- **Lookback window.** Each run re-reads a short overlap (`lookback_minutes`) to catch
  rows that land late. Upserts make the overlap harmless.
- **Batches.** Rows stream from BigQuery a page at a time and are written with
  `execute_values` in batches of `BATCH_SIZE`, one short transaction per batch.
- **State in the target.** The watermark is stored in Postgres and only moves forward
  (`GREATEST`), and only after the rows are written. A crash means the next run repeats
  some work; it never skips rows.
- **Dry run.** `?dry_run=true` (or `DRY_RUN=true`) queries BigQuery and reports row
  counts and the watermark it would save, without writing anything. It also works
  with no `PG_DSN` set.
- **Safe identifiers.** Table and column names from the config are checked against a
  strict pattern before they are put into SQL; values always go through parameters.

## Files

| File | Purpose |
|---|---|
| `main.py` | Flask app and sync logic |
| `tables.yml` | Tables, keys, columns, mode, watermark |
| `schema.sql` | Target tables in Postgres |
| `requirements.txt`, `Dockerfile` | Container build |
| `service.yaml` | Cloud Run service (max 1 instance, secret-backed DSN) |

## Environment variables

| Variable | Example | Notes |
|---|---|---|
| `PG_DSN` | `postgresql://sync_user:<password>@<host>:5432/postgres?sslmode=require` | From Secret Manager in production |
| `BQ_BILLING_PROJECT` | `your-gcp-project` | Project billed for BigQuery reads |
| `BATCH_SIZE` | `5000` | Rows per upsert batch |
| `DRY_RUN` | `false` | Default for requests that do not pass `dry_run` |
| `SYNC_CONFIG` | `/app/tables.yml` | Optional path override |

## Run locally

```bash
pip install -r requirements.txt
gcloud auth application-default login
export BQ_BILLING_PROJECT=your-gcp-project
python main.py orders --dry-run          # counts only, no Postgres needed
export PG_DSN=postgresql://postgres:postgres@localhost:5432/postgres
psql "$PG_DSN" -f schema.sql
python main.py                            # full first load, then incremental
```

## Deploy

```bash
PROJECT=your-gcp-project
REGION=us-central1

# Service account: read BigQuery, read the DSN secret
gcloud iam service-accounts create pg-sync --project $PROJECT
gcloud projects add-iam-policy-binding $PROJECT \
  --member serviceAccount:pg-sync@$PROJECT.iam.gserviceaccount.com --role roles/bigquery.jobUser
printf '%s' "$PG_DSN" | gcloud secrets create pg-sync-dsn --data-file=- --project $PROJECT
gcloud secrets add-iam-policy-binding pg-sync-dsn --project $PROJECT \
  --member serviceAccount:pg-sync@$PROJECT.iam.gserviceaccount.com --role roles/secretmanager.secretAccessor

# Build and deploy
gcloud builds submit --tag $REGION-docker.pkg.dev/$PROJECT/pipelines/warehouse-to-postgres-sync:latest --project $PROJECT
gcloud run services replace service.yaml --region $REGION --project $PROJECT
```

For your own (non-public) datasets also grant `roles/bigquery.dataViewer` on the source
dataset.

## Schedule with Cloud Scheduler

```bash
URL=$(gcloud run services describe warehouse-to-postgres-sync --region $REGION --project $PROJECT --format 'value(status.url)')

gcloud iam service-accounts create scheduler-invoker --project $PROJECT
gcloud run services add-iam-policy-binding warehouse-to-postgres-sync --region $REGION --project $PROJECT \
  --member serviceAccount:scheduler-invoker@$PROJECT.iam.gserviceaccount.com --role roles/run.invoker

gcloud scheduler jobs create http warehouse-to-postgres-sync \
  --project $PROJECT --location $REGION \
  --schedule "*/15 * * * *" --time-zone "Etc/UTC" \
  --uri "$URL/sync" --http-method POST \
  --oidc-service-account-email scheduler-invoker@$PROJECT.iam.gserviceaccount.com \
  --attempt-deadline 1800s
```

The Cloud Run service is capped at one instance with concurrency 1, so a slow run and
the next trigger never write at the same time.

## Extending

- Add a table: add an entry to `tables.yml` and its `CREATE TABLE` to `schema.sql`.
- Deletes: this pattern copies inserts and updates. If the source hard-deletes rows,
  add a periodic `full` reconciliation that compares primary keys, or have the source
  soft-delete with a `deleted_at` column included in the watermark.
