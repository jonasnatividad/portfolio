import functions_framework
import os
import json
import threading
import psycopg2
from psycopg2.extras import execute_values
from google.cloud import bigquery
from datetime import date, datetime
from decimal import Decimal

_sync_lock = threading.Lock()

SUPABASE_CONN = {
    "host": "db.hylnhmtplsriaedhmjis.supabase.co",
    "port": 5432,
    "dbname": "postgres",
    "user": "postgres",
    "password": os.environ["SUPABASE_DB_PASSWORD"],
    "sslmode": "require",
}

TABLES = [
    ("Prod.companies_prod",           "companies_prod",           "company_id"),
    ("Prod.deals_prod",               "deals_prod",               "deal_id"),
    ("Prod.g1_signal_investors_prod", "g1_signal_investors_prod", "investor_id"),
    ("Prod.investors_prod",           "investors_prod",           "investor_id"),
    ("Prod.signal_investors_prod",    "signal_investors_prod",    "investor_id"),
]

BATCH_SIZE = 2000

BQ_TO_PG_TYPE = {
    "STRING": "TEXT",
    "BYTES": "BYTEA",
    "INTEGER": "BIGINT",
    "INT64": "BIGINT",
    "FLOAT": "DOUBLE PRECISION",
    "FLOAT64": "DOUBLE PRECISION",
    "NUMERIC": "NUMERIC",
    "BIGNUMERIC": "NUMERIC",
    "BOOLEAN": "BOOLEAN",
    "BOOL": "BOOLEAN",
    "TIMESTAMP": "TIMESTAMPTZ",
    "DATE": "DATE",
    "TIME": "TIME",
    "DATETIME": "TIMESTAMP",
    "JSON": "JSONB",
    "RECORD": "JSONB",
    "STRUCT": "JSONB",
    "GEOGRAPHY": "TEXT",
}

def serialize(val):
    if val is None:
        return None
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    return val

def sync_table(conn, bq_client, bq_table, supabase_table, pk):
    print(f"[{supabase_table}] fetching schema...")
    table_ref = bq_client.get_table(bq_table)
    schema = table_ref.schema

    bq_cols = {}  # col_name -> pg_type, preserves order
    for field in schema:
        bq_cols[field.name] = BQ_TO_PG_TYPE.get(field.field_type, "TEXT")
    col_names = list(bq_cols.keys())

    # Create table if it doesn't exist, then add any new BQ columns.
    # Supabase-only columns are never touched.
    with conn.cursor() as cur:
        cols_sql = ", ".join(f'"{name}" {pg_type}' for name, pg_type in bq_cols.items())
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS "{supabase_table}" (
                {cols_sql},
                PRIMARY KEY ("{pk}")
            )
        """)

        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
        """, (supabase_table,))
        existing_cols = {row[0] for row in cur.fetchall()}

        for col_name, pg_type in bq_cols.items():
            if col_name not in existing_cols:
                print(f"[{supabase_table}] adding new column: {col_name} {pg_type}")
                cur.execute(f'ALTER TABLE "{supabase_table}" ADD COLUMN "{col_name}" {pg_type}')
    conn.commit()

    print(f"[{supabase_table}] fetching all rows from BigQuery...")
    rows = list(bq_client.query(f"SELECT * FROM `{bq_table}`").result())
    print(f"[{supabase_table}] got {len(rows)} rows — upserting...")

    data = [tuple(serialize(row[c]) for c in col_names) for row in rows]
    cols_list = ", ".join(f'"{c}"' for c in col_names)
    update_cols = [c for c in col_names if c != pk]
    update_clause = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in update_cols)
    insert_sql = (
        f'INSERT INTO "{supabase_table}" ({cols_list}) VALUES %s '
        f'ON CONFLICT ("{pk}") DO UPDATE SET {update_clause}'
    )

    for i in range(0, len(data), BATCH_SIZE):
        batch = data[i:i + BATCH_SIZE]
        with conn.cursor() as cur:
            execute_values(cur, insert_sql, batch)
        conn.commit()

    # Delete rows that no longer exist in BQ
    bq_pks = {row[pk] for row in rows}
    with conn.cursor() as cur:
        cur.execute(f'SELECT "{pk}" FROM "{supabase_table}"')
        supabase_pks = {row[0] for row in cur.fetchall()}

    stale_pks = list(supabase_pks - bq_pks)
    if stale_pks:
        print(f"[{supabase_table}] deleting {len(stale_pks)} stale rows...")
        for i in range(0, len(stale_pks), BATCH_SIZE):
            batch = stale_pks[i:i + BATCH_SIZE]
            with conn.cursor() as cur:
                cur.execute(f'DELETE FROM "{supabase_table}" WHERE "{pk}" = ANY(%s)', (batch,))
            conn.commit()

    print(f"[{supabase_table}] done — {len(rows)} rows")
    return len(rows)

@functions_framework.http
def sync(request):
    acquired = _sync_lock.acquire(blocking=False)
    if not acquired:
        print("Sync already in progress — skipping")
        return (json.dumps({"status": "skipped", "reason": "already running"}), 200,
                {"Content-Type": "application/json"})

    try:
        bq_client = bigquery.Client()
        conn = psycopg2.connect(**SUPABASE_CONN)
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '300s'")
        conn.commit()

        results = {}
        for bq_table, supabase_table, pk in TABLES:
            try:
                count = sync_table(conn, bq_client, bq_table, supabase_table, pk)
                results[supabase_table] = {"status": "ok", "rows": count}
            except Exception as e:
                print(f"[{supabase_table}] ERROR: {e}")
                results[supabase_table] = {"status": "error", "error": str(e)}
                conn.rollback()

        conn.close()
        return (json.dumps({"status": "complete", "tables": results}), 200,
                {"Content-Type": "application/json"})
    finally:
        _sync_lock.release()
