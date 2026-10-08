"""Incremental BigQuery -> Postgres replication service (Cloud Run).

POST /sync                      sync every table in tables.yml
POST /sync?table=orders         sync one table
POST /sync?dry_run=true         read from BigQuery and report counts, write nothing
GET  /healthz                   liveness check

For each table the service:
  1. reads the last watermark from the Postgres state table,
  2. selects rows from BigQuery whose watermark is newer (minus a lookback),
  3. upserts them into Postgres in batches (ON CONFLICT DO UPDATE),
  4. stores the highest watermark seen, in the same transaction as the last batch.

Configuration comes from environment variables (see README) and tables.yml.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import psycopg2
import psycopg2.extras
import yaml
from flask import Flask, jsonify, request
from google.cloud import bigquery

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("warehouse_to_postgres_sync")

CONFIG_PATH = Path(os.environ.get("SYNC_CONFIG", Path(__file__).with_name("tables.yml")))
BQ_BILLING_PROJECT = os.environ.get("BQ_BILLING_PROJECT", "your-gcp-project")
PG_DSN = os.environ.get("PG_DSN", "")  # e.g. postgresql://user:pass@host:5432/dbname?sslmode=require
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "5000"))
DEFAULT_DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
STATE_TABLE = "sync_state"
EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class TableConfig:
    name: str
    mode: str
    primary_key: list[str]
    columns: list[str]
    watermark_sql: str | None = None
    lookback_minutes: int = 0

    def validate(self) -> None:
        for ident in [self.name, *self.primary_key, *self.columns]:
            if not IDENTIFIER.match(ident):
                raise ValueError(f"Unsafe identifier in config: {ident!r}")
        if self.mode not in ("incremental", "full"):
            raise ValueError(f"{self.name}: mode must be incremental or full")
        if self.mode == "incremental" and not self.watermark_sql:
            raise ValueError(f"{self.name}: incremental mode needs watermark_sql")
        missing = set(self.primary_key) - set(self.columns)
        if missing:
            raise ValueError(f"{self.name}: primary key columns not in columns list: {missing}")


@dataclass
class SyncConfig:
    source_project: str
    source_dataset: str
    target_schema: str
    tables: list[TableConfig] = field(default_factory=list)


def load_config(path: Path = CONFIG_PATH) -> SyncConfig:
    raw = yaml.safe_load(path.read_text())
    tables = [TableConfig(**t) for t in raw["tables"]]
    for t in tables:
        t.validate()
    if not IDENTIFIER.match(raw["target_schema"]):
        raise ValueError("Unsafe target_schema")
    return SyncConfig(raw["source_project"], raw["source_dataset"], raw["target_schema"], tables)


# --------------------------------------------------------------------------- #
# Postgres helpers
# --------------------------------------------------------------------------- #

def ensure_state_table(conn, schema: str) -> None:
    with conn.cursor() as cur:
        cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{schema}".{STATE_TABLE} (
                table_name    text PRIMARY KEY,
                watermark     timestamptz NOT NULL,
                rows_last_run integer NOT NULL DEFAULT 0,
                synced_at     timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    conn.commit()


def read_watermark(conn, schema: str, table: str) -> dt.datetime:
    with conn.cursor() as cur:
        cur.execute(f'SELECT watermark FROM "{schema}".{STATE_TABLE} WHERE table_name = %s', (table,))
        row = cur.fetchone()
    return row[0] if row else EPOCH


def upsert_sql(schema: str, t: TableConfig) -> str:
    cols = ", ".join(f'"{c}"' for c in t.columns)
    pk = ", ".join(f'"{c}"' for c in t.primary_key)
    updates = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in t.columns if c not in t.primary_key)
    conflict = f"DO UPDATE SET {updates}" if updates else "DO NOTHING"
    return f'INSERT INTO "{schema}"."{t.name}" ({cols}) VALUES %s ON CONFLICT ({pk}) {conflict}'


def write_watermark(cur, schema: str, table: str, watermark: dt.datetime, rows: int) -> None:
    cur.execute(
        f"""
        INSERT INTO "{schema}".{STATE_TABLE} (table_name, watermark, rows_last_run, synced_at)
        VALUES (%s, %s, %s, now())
        ON CONFLICT (table_name) DO UPDATE
        SET watermark = GREATEST("{schema}".{STATE_TABLE}.watermark, EXCLUDED.watermark),
            rows_last_run = EXCLUDED.rows_last_run,
            synced_at = now()
        """,
        (table, watermark, rows),
    )


# --------------------------------------------------------------------------- #
# BigQuery helpers
# --------------------------------------------------------------------------- #

def build_query(cfg: SyncConfig, t: TableConfig) -> str:
    """watermark_sql comes from the reviewed tables.yml, never from a request."""
    source = f"`{cfg.source_project}.{cfg.source_dataset}.{t.name}`"
    cols = ", ".join(t.columns)
    if t.mode == "full":
        return f"SELECT {cols} FROM {source}"
    sql = (
        f"SELECT {cols}, {t.watermark_sql} AS _watermark FROM {source} "
        f"WHERE {t.watermark_sql} > TIMESTAMP_SUB(@since, INTERVAL @lookback MINUTE) "
        f"ORDER BY _watermark"
    )
    return sql


def fetch_rows(bq: bigquery.Client, cfg: SyncConfig, t: TableConfig, since: dt.datetime) -> Iterator[dict[str, Any]]:
    sql = build_query(cfg, t)
    params = []
    if t.mode == "incremental":
        params = [
            bigquery.ScalarQueryParameter("since", "TIMESTAMP", since),
            bigquery.ScalarQueryParameter("lookback", "INT64", t.lookback_minutes),
        ]
    job = bq.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
    for row in job.result(page_size=BATCH_SIZE):
        yield dict(row.items())


def batched(rows: Iterator[dict[str, Any]], size: int) -> Iterator[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


# --------------------------------------------------------------------------- #
# Sync
# --------------------------------------------------------------------------- #

def sync_table(bq, conn, cfg: SyncConfig, t: TableConfig, dry_run: bool) -> dict[str, Any]:
    since = read_watermark(conn, cfg.target_schema, t.name) if conn else EPOCH
    log.info("table=%s mode=%s since=%s dry_run=%s", t.name, t.mode, since.isoformat(), dry_run)

    total = 0
    max_watermark = since
    statement = upsert_sql(cfg.target_schema, t)

    for batch in batched(fetch_rows(bq, cfg, t, since), BATCH_SIZE):
        total += len(batch)
        if t.mode == "incremental":
            max_watermark = max(max_watermark, max(r["_watermark"] for r in batch))
        if dry_run:
            continue
        values = [tuple(r[c] for c in t.columns) for r in batch]
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, statement, values, page_size=1000)
        conn.commit()  # one transaction per batch keeps locks short
        log.info("table=%s upserted=%d", t.name, total)

    if not dry_run:
        watermark = max_watermark if t.mode == "incremental" else dt.datetime.now(dt.timezone.utc)
        with conn.cursor() as cur:
            write_watermark(cur, cfg.target_schema, t.name, watermark, total)
        conn.commit()

    return {
        "table": t.name,
        "mode": t.mode,
        "rows": total,
        "since": since.isoformat(),
        "new_watermark": max_watermark.isoformat() if t.mode == "incremental" else None,
        "dry_run": dry_run,
    }


def run_sync(table: str | None = None, dry_run: bool = DEFAULT_DRY_RUN) -> list[dict[str, Any]]:
    cfg = load_config()
    targets = [t for t in cfg.tables if table in (None, t.name)]
    if not targets:
        raise ValueError(f"Unknown table: {table}")

    bq = bigquery.Client(project=BQ_BILLING_PROJECT)
    conn = None
    if PG_DSN:
        conn = psycopg2.connect(PG_DSN)
        ensure_state_table(conn, cfg.target_schema)
    elif not dry_run:
        raise RuntimeError("PG_DSN is not set; use dry_run=true to test without Postgres")

    results = []
    try:
        for t in targets:
            try:
                results.append(sync_table(bq, conn, cfg, t, dry_run))
            except Exception as exc:  # keep going; report per-table failures
                log.exception("table=%s failed", t.name)
                if conn:
                    conn.rollback()
                results.append({"table": t.name, "error": str(exc)})
    finally:
        if conn:
            conn.close()
    return results


app = Flask(__name__)


@app.get("/healthz")
def healthz():
    return "ok", 200


@app.post("/sync")
def sync_endpoint():
    table = request.args.get("table")
    dry_run = request.args.get("dry_run", str(DEFAULT_DRY_RUN)).lower() == "true"
    results = run_sync(table=table, dry_run=dry_run)
    status = 500 if any("error" in r for r in results) else 200
    return jsonify({"results": results}), status


if __name__ == "__main__":
    # Local run: python main.py [table] [--dry-run]
    import sys

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for result in run_sync(table=args[0] if args else None, dry_run="--dry-run" in sys.argv):
        print(result)
