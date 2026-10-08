"""Cloud Run service: publish prod views to a Google Sheet for the sales team.

POST /refresh               check data quality, then rewrite each tab
POST /refresh?dry_run=true  run the queries and return row counts, write nothing
GET  /healthz

Each prod view maps to one worksheet. A tab is cleared and rewritten in a
single update call, and a "Status" tab records when the data was refreshed and
which file it came from, so readers can tell at a glance whether it is current.

Auth: the Cloud Run service account must be shared on the sheet as an Editor
(share the sheet with its email address). No key file is needed; gspread uses
the runtime's default credentials.
"""

from __future__ import annotations

import datetime as dt
import decimal
import logging
import os

import google.auth
import gspread
from flask import Flask, jsonify, request
from google.cloud import bigquery

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("sheet_refresh")

PROJECT = os.environ.get("GCP_PROJECT", "your-gcp-project")
SHEET_ID = os.environ.get("SHEET_ID", "")  # the long id in the sheet URL
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# worksheet title -> prod view
TABS = {
    "Pipeline by Stage": "sales_prod.pipeline_by_stage",
    "Rep Scorecard": "sales_prod.rep_scorecard",
    "Forecast by Month": "sales_prod.forecast_by_month",
}

bq = bigquery.Client(project=PROJECT)
app = Flask(__name__)


def to_cell(value):
    """Convert BigQuery values to something the Sheets API accepts."""
    if value is None:
        return ""
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


def query_table(view: str) -> list[list]:
    rows = bq.query(f"SELECT * FROM `{PROJECT}.{view}`").result()
    header = [f.name for f in rows.schema]
    return [header] + [[to_cell(v) for v in row.values()] for row in rows]


def failing_quality_checks() -> list[dict]:
    sql = f"""
        SELECT check_name, severity, failing_rows
        FROM `{PROJECT}.sales_live.data_quality`
        WHERE failing_rows > 0
    """
    return [dict(r.items()) for r in bq.query(sql).result()]


def latest_source_file() -> str:
    sql = f"SELECT MAX(_source_file) AS f FROM `{PROJECT}.sales_raw.deals`"
    return next(iter(bq.query(sql).result())).f or ""


def open_sheet() -> gspread.Spreadsheet:
    credentials, _ = google.auth.default(scopes=SCOPES)
    return gspread.authorize(credentials).open_by_key(SHEET_ID)


def write_tab(sheet: gspread.Spreadsheet, title: str, values: list[list]) -> None:
    try:
        ws = sheet.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(title=title, rows=max(len(values), 10), cols=max(len(values[0]), 5))
    ws.clear()
    ws.update(values, "A1", value_input_option="USER_ENTERED")
    ws.freeze(rows=1)


@app.post("/refresh")
def refresh():
    dry_run = request.args.get("dry_run", "false").lower() == "true"

    problems = failing_quality_checks()
    blocking = [p for p in problems if p["severity"] == "block"]
    if blocking and not dry_run:
        log.error("not publishing, blocking checks failed: %s", blocking)
        return jsonify({"status": "blocked", "checks": blocking}), 409

    data = {title: query_table(view) for title, view in TABS.items()}
    summary = {title: len(values) - 1 for title, values in data.items()}
    if dry_run:
        return jsonify({"status": "dry_run", "rows": summary, "quality_issues": problems}), 200

    if not SHEET_ID:
        return jsonify({"status": "error", "reason": "SHEET_ID is not set"}), 500

    sheet = open_sheet()
    for title, values in data.items():
        write_tab(sheet, title, values)

    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    status_rows = [["Last refreshed", now], ["Source file", latest_source_file()]]
    status_rows += [[f"Warning: {p['check_name']}", p["failing_rows"]] for p in problems]
    write_tab(sheet, "Status", status_rows)

    log.info("published %s", summary)
    return jsonify({"status": "published", "rows": summary, "warnings": problems}), 200


@app.get("/healthz")
def healthz():
    return "ok", 200
