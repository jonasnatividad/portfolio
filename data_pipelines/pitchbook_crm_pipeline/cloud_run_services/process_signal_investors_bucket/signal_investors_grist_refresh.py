import os
import json
import math
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.exceptions import HTTPError

from google.cloud import bigquery, storage
from google.cloud.bigquery import SchemaField, Table, LoadJobConfig

# ================== Config ==================
PROJECT_ID     = os.environ.get("BQ_PROJECT",    "your-project-id")
PROD_TABLE_FQN = os.environ.get("PROD_TABLE",    f"{PROJECT_ID}.Prod.signal_investors_prod")

# Overlay mirror (Grist custom fields → BigQuery) — enable with UPSYNC_OVERLAY=1
OVERLAY_DATASET = os.environ.get("OVERLAY_DATASET", "App")
OVERLAY_TABLE   = os.environ.get("OVERLAY_TABLE",   "overlay_signal_investors_current")
UPSYNC_OVERLAY  = os.environ.get("UPSYNC_OVERLAY",  "0") == "1"

# Grist
GRIST_BASE    = "https://docs.getgrist.com"
GRIST_DOC     = os.environ.get("GRIST_DOC",     "your-grist-doc-id")
GRIST_TABLE   = os.environ.get("GRIST_TABLE",   "Signal_Investors"))
GRIST_API_KEY = os.environ.get("GRIST_API_KEY", "your-grist-api-key")

# State persisted in GCS (survives cold starts)
ARCHIVE_BUCKET = os.environ.get("ARCHIVE_BUCKET", "pitchbook-signal-investors-archive")
STATE_BLOB     = os.environ.get("STATE_BLOB",     "states/.state_signal_investors.json")

# Key column — must exist in both BigQuery and Grist, unique in the prod view
KEY_COL = "investor_id"

# Batching
BQ_PAGE_LIMIT     = int(os.environ.get("BQ_PAGE_LIMIT",             "100000"))
INSERT_BATCH_SIZE = int(os.environ.get("INSERT_BATCH_SIZE",         "200"))
PATCH_BATCH_SIZE  = int(os.environ.get("PATCH_BATCH_SIZE",          "200"))
BQ_JOB_TIMEOUT    = int(os.environ.get("BQ_JOB_TIMEOUT",           "180"))
MAX_PAGES         = int(os.environ.get("MAX_PAGES_PER_INVOCATION",  "200"))

# Parallelism
PATCH_WORKERS = int(os.environ.get("PATCH_WORKERS", "8"))
POST_WORKERS  = int(os.environ.get("POST_WORKERS",  "6"))

# ============================================

bq             = bigquery.Client(project=PROJECT_ID)
storage_client = storage.Client(project=PROJECT_ID)

sess = requests.Session()
retry = Retry(
    total=6, backoff_factor=0.5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=frozenset(["GET", "POST", "PATCH"])
)
adapter = HTTPAdapter(pool_connections=64, pool_maxsize=64, max_retries=retry)
sess.mount("https://", adapter)
sess.mount("http://",  adapter)
sess.headers.update({
    "Authorization":   f"Bearer {GRIST_API_KEY}",
    "Content-Type":    "application/json",
    "Accept":          "application/json",
    "Accept-Encoding": "gzip",
})

# ============== Utils ========================
def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat()} | {msg}", flush=True)

def load_state() -> Dict:
    try:
        blob = storage_client.bucket(ARCHIVE_BUCKET).blob(STATE_BLOB)
        if not blob.exists():
            raise FileNotFoundError
        s = json.loads(blob.download_as_text())
        log(f"Loaded state gs://{ARCHIVE_BUCKET}/{STATE_BLOB}: {s}")
        return s
    except Exception:
        s = {"last_downsync": None}
        log(f"No state found; init: {s}")
        return s

def save_state(s: Dict) -> None:
    storage_client.bucket(ARCHIVE_BUCKET).blob(STATE_BLOB) \
        .upload_from_string(json.dumps(s), content_type="application/json")
    log(f"Saved state → gs://{ARCHIVE_BUCKET}/{STATE_BLOB}: {s}")

def _json_default(obj):
    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=timezone.utc)
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    return str(obj)

def _normalize_value(v):
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()
    return v

def normalize_fields(fields: Dict) -> Dict:
    return {k: _normalize_value(v) for k, v in (fields or {}).items()
            if v is not None and _normalize_value(v) is not None}

def safe_json_dumps(payload: Dict) -> str:
    return json.dumps(payload, default=_json_default, allow_nan=False)

# ============== Grist helpers ================
def grist_health() -> None:
    sess.get(f"{GRIST_BASE}/api/docs/{GRIST_DOC}/tables").raise_for_status()
    log("Health: Grist OK")

def grist_columns() -> List[Dict]:
    log("GET /columns ...")
    r = sess.get(f"{GRIST_BASE}/api/docs/{GRIST_DOC}/tables/{GRIST_TABLE}/columns")
    r.raise_for_status()
    cols = r.json().get("columns", r.json())
    log(f"Grist columns: {len(cols)}")
    return cols

def iter_grist_records(page: int = 100000):
    log(f"Iterating Grist /records (page={page}) ...")
    offset, total = 0, 0
    while True:
        r = sess.get(
            f"{GRIST_BASE}/api/docs/{GRIST_DOC}/tables/{GRIST_TABLE}/records",
            params={"limit": page, "offset": offset},
        )
        r.raise_for_status()
        chunk = r.json().get("records", []) or []
        n = len(chunk)
        total += n
        log(f"Grist page offset={offset}: {n} records")
        if not n:
            break
        yield from chunk
        if n < page:
            break
        offset += page
    log(f"Grist total records scanned: {total}")

def grist_post_records(records: List[Dict]) -> None:
    if not records:
        return
    payload = {"records": [{"fields": r} for r in records]}
    r = sess.post(
        f"{GRIST_BASE}/api/docs/{GRIST_DOC}/tables/{GRIST_TABLE}/records",
        data=safe_json_dumps(payload),
    )
    if not r.ok:
        log(f"Grist POST failed: {r.status_code} {r.text}")
        r.raise_for_status()

def grist_patch_records(id_and_fields: List[Tuple[int, Dict]]) -> None:
    if not id_and_fields:
        return
    body = {"records": [{"id": rid, "fields": fields} for rid, fields in id_and_fields]}
    r = sess.patch(
        f"{GRIST_BASE}/api/docs/{GRIST_DOC}/tables/{GRIST_TABLE}/records",
        data=safe_json_dumps(body),
    )
    if not r.ok:
        log(f"Grist PATCH failed: {r.status_code} {r.text}")
        r.raise_for_status()

def build_key_index(records_iter, key_col: str) -> Dict[str, Tuple[int, int]]:
    idx: Dict[str, Tuple[int, int]] = {}
    scanned = 0
    for rec in records_iter:
        scanned += 1
        rid = int(rec.get("id"))
        fields = rec.get("fields", {}) or {}
        key = fields.get(key_col)
        if key is None:
            continue
        key = str(key)
        rev = int(fields.get("_rev") or 0)
        prev = idx.get(key)
        if prev is None or rev > prev[1]:
            idx[key] = (rid, rev)
    log(f"Key index: {len(idx)} entries (scanned {scanned})")
    return idx

# ============== BigQuery helpers =============
def bq_health() -> None:
    log("Health: BQ SELECT 1 ...")
    bq.query("SELECT 1").result(timeout=BQ_JOB_TIMEOUT)
    log("Health: BQ OK")

def bq_schema_names(table_fqn: str) -> List[str]:
    names = [f.name for f in bq.get_table(table_fqn).schema]
    log(f"BQ schema columns: {len(names)}")
    return names

def query_prod_page(wm: Optional[str], limit: int) -> List:
    if wm:
        sql = f"SELECT * FROM `{PROD_TABLE_FQN}` WHERE ingested_at > @wm ORDER BY ingested_at LIMIT {limit}"
        cfg = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("wm", "TIMESTAMP", wm)]
        )
    else:
        sql = f"SELECT * FROM `{PROD_TABLE_FQN}` ORDER BY ingested_at LIMIT {limit}"
        cfg = None
    log("BQ query prod page ...")
    return list(bq.query(sql, job_config=cfg).result(timeout=BQ_JOB_TIMEOUT))

# ============== Parallel patch / post ========
def _patch_bucket(items: List[Tuple[int, Dict]], batch: int) -> int:
    total, i, n = 0, 0, len(items)
    while i < n:
        j = min(i + batch, n)
        grist_patch_records(items[i:j])
        total += j - i
        i = j
    return total

def _patch_in_batches(id_and_fields: List[Tuple[int, Dict]], batch: int) -> int:
    if not id_and_fields:
        return 0
    buckets: Dict[Tuple, List] = {}
    for rid, fields in id_and_fields:
        sig = tuple(sorted(fields.keys()))
        buckets.setdefault(sig, []).append((rid, fields))
    log(f"PATCH buckets: {len(buckets)} unique field-sets")
    total = 0
    with ThreadPoolExecutor(max_workers=PATCH_WORKERS) as exe:
        futures = [exe.submit(_patch_bucket, items, batch)
                   for items in sorted(buckets.values(), key=len, reverse=True)]
        for f in as_completed(futures):
            total += f.result()
    return total

def _post_bucket(recs: List[Dict], batch: int) -> int:
    total, i, n = 0, 0, len(recs)
    while i < n:
        j = min(i + batch, n)
        grist_post_records(recs[i:j])
        total += j - i
        i = j
    return total

def _post_in_batches(records: List[Dict], batch: int) -> int:
    if not records:
        return 0
    n = len(records)
    chunk_size = max(batch * 4, n // max(1, POST_WORKERS))
    chunks, i = [], 0
    while i < n:
        j = min(i + chunk_size, n)
        chunks.append(records[i:j])
        i = j
    total = 0
    with ThreadPoolExecutor(max_workers=max(1, POST_WORKERS)) as exe:
        futures = [exe.submit(_post_bucket, c, batch) for c in chunks]
        for f in as_completed(futures):
            total += f.result()
    return total

# ============== Downsync (BQ → Grist) ========
def downsync_prod_to_grist(
    wm: Optional[str],
    vendor_ids: set,
    key_index: Dict[str, Tuple[int, int]],
) -> Tuple[Optional[str], bool]:
    page = query_prod_page(wm, BQ_PAGE_LIMIT)
    log(f"BQ returned rows: {len(page)}")
    if not page:
        return wm, False

    inserts: List[Dict] = []
    updates: List[Tuple[int, Dict]] = []
    latest_wm = wm

    for row in page:
        d = dict(row.items())
        fields = normalize_fields({cid: d[cid] for cid in vendor_ids if cid in d})
        key_val = str(d.get(KEY_COL) or "")
        if not key_val:
            continue

        known = key_index.get(key_val)
        if known:
            rid, _ = known
            if fields:
                updates.append((rid, fields))
        else:
            if fields:
                inserts.append(fields)

        ts = d.get("ingested_at")
        if ts:
            latest_wm = str(ts)

    total_upd = _patch_in_batches(updates, PATCH_BATCH_SIZE)
    total_ins = _post_in_batches(inserts, INSERT_BATCH_SIZE)
    log(f"Downsync page: patched {total_upd}, inserted {total_ins}")
    return latest_wm, bool(total_upd or total_ins)

# ============== Upsync (Grist → BQ overlay) ==
SYSTEM_IDS = {"id", "manualSort", "createdAt", "updatedAt", "_rev", "_rowId"}

def discover_custom_ids(grist_cols: List[Dict], vendor_ids: set) -> List[str]:
    return sorted({c["id"] for c in grist_cols} - vendor_ids - SYSTEM_IDS)

def build_overlay_rows(grist_records: List[Dict], key_col: str, custom_ids: List[str]) -> List[Dict]:
    by_key: Dict[str, Tuple[int, Dict]] = {}
    for rec in grist_records:
        fields = rec.get("fields", {}) or {}
        key = fields.get(key_col)
        if key is None:
            continue
        key = str(key)
        rev = int(fields.get("_rev") or 0)
        custom = {cid: fields[cid] for cid in custom_ids if cid in fields and fields[cid] is not None}
        prev = by_key.get(key)
        if prev is None or rev > prev[0]:
            by_key[key] = (rev, custom)
    return [{key_col: k, "custom": v} for k, (_, v) in by_key.items()]

def ensure_overlay_table(dest_fqn: str) -> None:
    try:
        bq.get_table(dest_fqn)
    except Exception:
        schema = [
            SchemaField("investor_id", "STRING"),
            SchemaField("custom",     "JSON"),
            SchemaField("updated_at", "TIMESTAMP"),
        ]
        bq.create_table(Table(dest_fqn, schema=schema))
        log(f"Created overlay table {dest_fqn}")

def load_overlay_temp(rows: List[Dict], dataset: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    temp_fqn = f"{PROJECT_ID}.{dataset}._overlay_signal_investors_upserts_{ts}"
    schema = [SchemaField("investor_id", "STRING"), SchemaField("custom", "JSON")]
    bq.create_table(Table(temp_fqn, schema=schema))
    bq.load_table_from_json(rows, temp_fqn, job_config=LoadJobConfig()).result(timeout=BQ_JOB_TIMEOUT)
    log(f"Loaded {len(rows)} overlay rows into temp {temp_fqn}")
    return temp_fqn

def merge_overlay(temp_fqn: str, dest_fqn: str) -> None:
    sql = f"""
    MERGE `{dest_fqn}` T
    USING (SELECT company_id, custom, CURRENT_TIMESTAMP() AS ts FROM `{temp_fqn}`) S
    ON T.investor_id = S.investor_id
    WHEN MATCHED     THEN UPDATE SET T.custom = S.custom, T.updated_at = S.ts
    WHEN NOT MATCHED THEN INSERT (investor_id, custom, updated_at) VALUES (S.investor_id, S.custom, S.ts)
    """
    bq.query(sql).result(timeout=BQ_JOB_TIMEOUT)
    log("Overlay MERGE complete.")

def drop_table(fqn: str) -> None:
    bq.delete_table(fqn, not_found_ok=True)
    log(f"Dropped temp table {fqn}")

# =================== Main ====================
def main():
    grist_health()
    bq_health()

    cols      = grist_columns()
    grist_ids = [c["id"] for c in cols]
    bq_names  = bq_schema_names(PROD_TABLE_FQN)
    vendor_ids = set(grist_ids) & set(bq_names)
    log(f"Vendor columns (id intersection): {len(vendor_ids)}")

    key_index = build_key_index(iter_grist_records(), KEY_COL)
    st = load_state()
    wm = st.get("last_downsync")
    page_count = 0

    while True:
        page_count += 1
        new_wm, did_mutate = downsync_prod_to_grist(wm, vendor_ids, key_index)

        if new_wm == wm or not did_mutate:
            log(f"Downsync complete. pages={page_count}")
            break

        wm = new_wm
        st["last_downsync"] = wm
        save_state(st)
        key_index = build_key_index(iter_grist_records(), KEY_COL)
        log(f"=== Next downsync page (wm={wm}) ===")

        if page_count >= MAX_PAGES:
            log(f"Hit MAX_PAGES_PER_INVOCATION={MAX_PAGES}. Saving state and exiting.")
            break

    if UPSYNC_OVERLAY:
        log("=== Upsync Grist custom fields → BigQuery overlay ===")
        custom_ids = discover_custom_ids(cols, vendor_ids)
        log(f"Custom field ids: {custom_ids or '[]'}")
        if custom_ids:
            grist_recs = list(iter_grist_records())
            overlay_rows = build_overlay_rows(grist_recs, KEY_COL, custom_ids)
            log(f"Overlay rows: {len(overlay_rows)}")
            if overlay_rows:
                dest_fqn = f"{PROJECT_ID}.{OVERLAY_DATASET}.{OVERLAY_TABLE}"
                ensure_overlay_table(dest_fqn)
                temp_fqn = load_overlay_temp(overlay_rows, OVERLAY_DATASET)
                try:
                    merge_overlay(temp_fqn, dest_fqn)
                finally:
                    drop_table(temp_fqn)
        else:
            log("No custom columns in Grist; skipping overlay upsync.")

    log("Sync complete.")

if __name__ == "__main__":
    main()
