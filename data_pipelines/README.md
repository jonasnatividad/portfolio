# Data Pipelines

Ingestion and replication services on Google Cloud, each deployable as a Cloud Run service.

- [`warehouse_to_postgres_sync/`](warehouse_to_postgres_sync) - Incremental BigQuery to Postgres replication driven by a table config (watermarks, batch upserts, dry run)
- [`file_drop_to_bigquery/`](file_drop_to_bigquery) - CSV files dropped in Cloud Storage, loaded to BigQuery, modeled in clean/live/prod views and published to Google Sheets
