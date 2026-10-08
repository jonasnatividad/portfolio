"""Cloud Run service: load CSV files dropped in Cloud Storage into BigQuery raw tables.

Trigger: Eventarc, event type google.cloud.storage.object.v1.finalized, on the
drop bucket. Eventarc POSTs the object metadata as JSON ({"bucket", "name",
"generation", ...}) to "/".

Routing: the folder decides the table.
    incoming/companies/companies_2026-09-30.csv  ->  sales_raw.companies
    incoming/deals/deals_2026-10-01.csv          ->  sales_raw.deals

For each file the service:
  1. ignores objects outside incoming/ or not ending in .csv,
  2. skips the file if this exact object generation is already in _load_log,
  3. checks the header row against the expected columns,
  4. loads the CSV (all columns STRING) into a temporary staging table,
  5. inserts staging rows into the raw table with load metadata,
  6. records the outcome and moves the object to processed/ or rejected/.

Returns 2xx for files that are done (loaded, skipped or rejected) so Eventarc
does not retry them; returns 5xx only for transient errors worth a retry.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import logging
import os
import re
import uuid

from flask import Flask, jsonify, request
from google.api_core import exceptions as gexc
from google.cloud import bigquery, storage

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("loader")

PROJECT = os.environ.get("GCP_PROJECT", "your-gcp-project")
RAW_DATASET = os.environ.get("RAW_DATASET", "sales_raw")
STAGING_DATASET = os.environ.get("STAGING_DATASET", RAW_DATASET)
INCOMING_PREFIX = "incoming/"

EXPECTED_COLUMNS: dict[str, list[str]] = {
    "companies": ["company_id", "company_name", "industry", "employee_band", "country",
                  "account_owner", "created_date"],
    "deals": ["deal_id", "company_id", "deal_name", "plan", "stage", "amount_usd", "owner",
              "created_date", "expected_close_date", "last_updated_at"],
}
FILE_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")

app = Flask(__name__)
_clients: dict = {}


def bq() -> bigquery.Client:
    """Created on first use, so the module imports (and its pure functions test) without credentials."""
    if "bq" not in _clients:
        _clients["bq"] = bigquery.Client(project=PROJECT)
    return _clients["bq"]


def gcs() -> storage.Client:
    if "gcs" not in _clients:
        _clients["gcs"] = storage.Client(project=PROJECT)
    return _clients["gcs"]


class RejectedFile(Exception):
    """The file is permanently unusable; move it aside and do not retry."""


def route(object_name: str) -> str | None:
    if not object_name.startswith(INCOMING_PREFIX) or not object_name.lower().endswith(".csv"):
        return None
    parts = object_name[len(INCOMING_PREFIX):].split("/")
    return parts[0] if len(parts) == 2 and parts[0] in EXPECTED_COLUMNS else None


def already_loaded(source: str, generation: str) -> bool:
    sql = f"""
        SELECT COUNT(*) AS n FROM `{PROJECT}.{RAW_DATASET}._load_log`
        WHERE source_file = @source AND generation = @generation AND status = 'loaded'
    """
    cfg = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("source", "STRING", source),
        bigquery.ScalarQueryParameter("generation", "STRING", generation),
    ])
    return next(iter(bq().query(sql, job_config=cfg).result())).n > 0


def parse_header(head: str) -> list[str]:
    """First CSV row of the file's opening bytes, trimmed and lower-cased."""
    first_line = head.lstrip("\ufeff").splitlines()[0] if head else ""
    return [h.strip().lower() for h in next(csv.reader(io.StringIO(first_line)), [])]


def check_header(blob: storage.Blob, table: str) -> None:
    head = blob.download_as_bytes(start=0, end=4095).decode("utf-8-sig", errors="replace")
    header = parse_header(head)
    expected = EXPECTED_COLUMNS[table]
    if header != expected:
        raise RejectedFile(f"header mismatch for {table}: got {header}, expected {expected}")


def load_file(bucket: str, name: str, table: str) -> int:
    uri = f"gs://{bucket}/{name}"
    staging = f"{PROJECT}.{STAGING_DATASET}._stage_{table}_{uuid.uuid4().hex[:12]}"
    columns = EXPECTED_COLUMNS[table]

    load_cfg = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        schema=[bigquery.SchemaField(c, "STRING") for c in columns],
        allow_quoted_newlines=True,
        max_bad_records=0,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    try:
        bq().load_table_from_uri(uri, staging, job_config=load_cfg).result()
    except gexc.BadRequest as exc:  # malformed CSV: permanent
        raise RejectedFile(f"BigQuery could not parse the CSV: {exc.message}") from exc

    try:
        # Expire the staging table even if the delete below never runs.
        tbl = bq().get_table(staging)
        tbl.expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=6)
        bq().update_table(tbl, ["expires"])

        match = FILE_DATE.search(name)
        cols = ", ".join(columns)
        insert = f"""
            INSERT INTO `{PROJECT}.{RAW_DATASET}.{table}` ({cols}, _source_file, _file_date, _loaded_at)
            SELECT {cols}, @source, @file_date, CURRENT_TIMESTAMP()
            FROM `{staging}`
        """
        cfg = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("source", "STRING", uri),
            bigquery.ScalarQueryParameter("file_date", "DATE", match.group(1) if match else None),
        ])
        job = bq().query(insert, job_config=cfg)
        job.result()
        return job.num_dml_affected_rows or 0
    finally:
        bq().delete_table(staging, not_found_ok=True)


def log_outcome(source: str, generation: str, table: str, rows: int | None, status: str, message: str = "") -> None:
    errors = bq().insert_rows_json(f"{PROJECT}.{RAW_DATASET}._load_log", [{
        "source_file": source,
        "generation": generation,
        "target_table": table,
        "row_count": rows,
        "status": status,
        "message": message[:1000],
        "loaded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }])
    if errors:
        log.error("could not write load log: %s", errors)


def move(bucket_name: str, name: str, folder: str) -> None:
    bucket = gcs().bucket(bucket_name)
    blob = bucket.blob(name)
    target = folder + name[len(INCOMING_PREFIX):]
    bucket.copy_blob(blob, bucket, target)
    blob.delete()
    log.info("moved %s -> %s", name, target)


@app.post("/")
def handle_event():
    event = request.get_json(silent=True) or {}
    bucket, name = event.get("bucket"), event.get("name")
    generation = str(event.get("generation", ""))
    if not bucket or not name:
        return jsonify({"status": "ignored", "reason": "not a storage event"}), 200

    table = route(name)
    if table is None:
        return jsonify({"status": "ignored", "object": name}), 200

    source = f"gs://{bucket}/{name}"
    if already_loaded(source, generation):
        log.info("skip duplicate event for %s#%s", source, generation)
        return jsonify({"status": "skipped", "object": name}), 200

    blob = gcs().bucket(bucket).get_blob(name)
    if blob is None:  # already moved by an earlier delivery of the same event
        return jsonify({"status": "skipped", "reason": "object no longer in incoming/"}), 200

    try:
        check_header(blob, table)
        rows = load_file(bucket, name, table)
    except RejectedFile as exc:
        log.warning("rejected %s: %s", source, exc)
        log_outcome(source, generation, table, None, "rejected", str(exc))
        move(bucket, name, "rejected/")
        return jsonify({"status": "rejected", "object": name, "reason": str(exc)}), 200

    log_outcome(source, generation, table, rows, "loaded")
    move(bucket, name, "processed/")
    log.info("loaded %s rows from %s into %s", rows, source, table)
    return jsonify({"status": "loaded", "object": name, "table": table, "rows": rows}), 200


@app.get("/healthz")
def healthz():
    return "ok", 200
