import os, re, json, tempfile, traceback, datetime
from datetime import timezone
from typing import Optional, List, Dict, Any

import pandas as pd
from google.cloud import storage, bigquery
# ========= Config =========
PROJECT_ID = os.environ.get("BQ_PROJECT", "your-project-id")

SOURCE_BUCKET  = os.environ.get("SOURCE_BUCKET",  "pitchbook-investors")
ARCHIVE_BUCKET = os.environ.get("ARCHIVE_BUCKET", "pitchbook-investors-archive")

TARGET_DATASET = os.environ.get("TARGET_DATASET", "Pitchbook")
TARGET_TABLE   = os.environ.get("TARGET_TABLE",   "investors_raw")

# PitchBook exports always have headers on Excel row 8 → pandas header index 7
HEADER_INDEX = 7

# Idempotency / locking (handles at-least-once delivery from GCS events)
PROCESSED_PREFIX = os.environ.get("PROCESSED_PREFIX", "states/processed")

# ========= Clients =========
storage_client = storage.Client(project=PROJECT_ID)
bq_client      = bigquery.Client(project=PROJECT_ID)

def log(msg: str):
    print(f"{datetime.datetime.now(timezone.utc).isoformat()} | {msg}", flush=True)

# ========= Header normalization =========
_FORBIDDEN = r'!"\$\(\)\*,\./;?\@\[\\\]\^`{}\~'
_FORBIDDEN_RE = re.compile(f"[{_FORBIDDEN}]")
_NON_ALNUM_UNDERSCORE = re.compile(r"[^a-z0-9_]+")

def _strip_hidden_and_forbidden(s: str) -> str:
    s = "" if s is None else str(s)
    s = s.replace("\u200b", "").replace("\ufeff", "").replace("\u00a0", " ")
    s = _FORBIDDEN_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:300].rstrip()

def to_snake_header(name: str) -> str:
    s = _strip_hidden_and_forbidden(name).lower().replace("#", "number")
    s = _NON_ALNUM_UNDERSCORE.sub("_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "column"
    if s[0].isdigit():
        s = "_" + s
    return s[:300].rstrip("_")

def dedupe_snake(cols: List[str]) -> List[str]:
    out, seen = [], {}
    for c in cols:
        if c in seen:
            seen[c] += 1
            out.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            out.append(c)
    return out

# ========= Excel reading =========
def read_xlsx(xlsx_path: str) -> pd.DataFrame:
    df = pd.read_excel(xlsx_path, header=HEADER_INDEX, dtype=str)
    log(f"Initial DataFrame shape: {df.shape}")
    return df

# ========= Cleaning =========
def normalize_and_clean_df(df: pd.DataFrame):
    log(f"Normalizing DataFrame shape {df.shape}")

    original_cols = list(map(str, df.columns))
    snake_cols = dedupe_snake([to_snake_header(c) for c in original_cols])
    col_map = dict(zip(original_cols, snake_cols))
    df.columns = snake_cols

    for col in df.columns:
        if col == "ingested_at":
            continue
        df[col] = df[col].apply(lambda x: str(x) if (x is not None and x != "nan") else None)

    # Drop fully empty rows
    df = df.loc[
        ~df.apply(
            lambda row: all(
                (v is None) or (isinstance(v, str) and not v.strip())
                for v in row
            ),
            axis=1
        )
    ]

    df["ingested_at"] = datetime.datetime.now(timezone.utc)
    return df, col_map

# ========= BigQuery =========
def ensure_dataset_exists(dataset_id: str):
    try:
        bq_client.get_dataset(dataset_id)
    except Exception:
        ds = bigquery.Dataset(dataset_id)
        ds.location = "US"
        bq_client.create_dataset(ds)

def ensure_table_exists(table_id: str, df: pd.DataFrame):
    try:
        bq_client.get_table(table_id)
        return
    except Exception:
        pass
    schema = [
        bigquery.SchemaField(c, "TIMESTAMP" if c == "ingested_at" else "STRING")
        for c in df.columns
    ]
    bq_client.create_table(bigquery.Table(table_id, schema=schema))
    log(f"Created table {table_id}")

# ========= Idempotency — LOCK + DONE markers =========
def _safe_marker_name(blob_name: str) -> str:
    return blob_name.replace("/", "__")

def _lock_name(blob_name: str, generation: Optional[int]) -> str:
    gen = str(generation) if generation is not None else "nogeneration"
    return f"{PROCESSED_PREFIX}/{_safe_marker_name(blob_name)}.{gen}.lock"

def _done_name(blob_name: str, generation: Optional[int]) -> str:
    gen = str(generation) if generation is not None else "nogeneration"
    return f"{PROCESSED_PREFIX}/{_safe_marker_name(blob_name)}.{gen}.done"

def already_done(blob_name: str, generation: Optional[int]) -> bool:
    return storage_client.bucket(ARCHIVE_BUCKET).blob(_done_name(blob_name, generation)).exists()

def acquire_lock(blob_name: str, generation: Optional[int]) -> bool:
    """
    Write a lock object with if_generation_match=0 so only one concurrent
    invocation can proceed. Returns True if acquired, False if lock already exists.
    """
    dst_bucket = storage_client.bucket(ARCHIVE_BUCKET)
    lock_blob = dst_bucket.blob(_lock_name(blob_name, generation))
    try:
        lock_blob.upload_from_string(
            json.dumps({
                "blob": blob_name,
                "generation": generation,
                "locked_at": datetime.datetime.now(timezone.utc).isoformat(),
            }),
            if_generation_match=0,
        )
        return True
    except Exception:
        return False

def mark_done(blob_name: str, generation: Optional[int]) -> None:
    """
    Write DONE marker after Grist refresh succeeds. Called from main.py, not here.
    """
    storage_client.bucket(ARCHIVE_BUCKET).blob(_done_name(blob_name, generation)).upload_from_string(
        json.dumps({
            "blob": blob_name,
            "generation": generation,
            "done_at": datetime.datetime.now(timezone.utc).isoformat(),
        })
    )

# ========= Archiving =========
def upload_sidecar(original_blob_name: str, mapping: Dict) -> None:
    archive_bucket = storage_client.bucket(ARCHIVE_BUCKET)
    archive_bucket.blob(f"{original_blob_name}.columns.json").upload_from_string(
        json.dumps(mapping, indent=2)
    )

def move_blob_to_archive(blob_name: str) -> None:
    src_bucket = storage_client.bucket(SOURCE_BUCKET)
    dst_bucket = storage_client.bucket(ARCHIVE_BUCKET)
    src = src_bucket.blob(blob_name)

    if not src.exists():
        log(f"Source blob missing (likely already archived): {blob_name}")
        return

    dst_bucket.copy_blob(src, dst_bucket, blob_name)
    try:
        src.delete()
    except Exception as e:
        log(f"Warning: failed deleting source (may already be gone): {blob_name} | {e}")

# ========= Main =========
def process_files(blob_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Process a specific blob (triggered by GCS finalize event) or all .xlsx in SOURCE_BUCKET.

    Idempotency strategy:
      - Checks DONE marker: skips if this exact name+generation was already fully processed
      - Acquires LOCK: prevents two concurrent invocations from both doing work
      - DONE marker is NOT written here — main.py writes it after Grist refresh succeeds

    Returns:
      {
        "status":    "ok" | "error" | "no_files",
        "did_work":  bool,
        "processed": [{"name": ..., "generation": ...}],
        "skipped":   [{"name": ..., "generation": ..., "reason": ...}],
        "errors":    [{"name": ..., "generation": ..., "error": ...}]
      }
    """
    result: Dict[str, Any] = {
        "status": "ok",
        "did_work": False,
        "processed": [],
        "skipped": [],
        "errors": [],
    }

    try:
        log("=== GCS → BQ START ===")
        source_bucket = storage_client.bucket(SOURCE_BUCKET)

        blobs = [source_bucket.blob(blob_name)] if blob_name else [
            b for b in source_bucket.list_blobs()
            if b.name.lower().endswith(".xlsx")
        ]
        if not blobs:
            result["status"] = "no_files"
            return result

        dataset_ref = f"{PROJECT_ID}.{TARGET_DATASET}"
        table_ref   = f"{dataset_ref}.{TARGET_TABLE}"
        ensure_dataset_exists(dataset_ref)

        for i, blob in enumerate(blobs):
            log(f"Processing {blob.name}")

            try:
                blob.reload()
            except Exception as e:
                msg = f"Blob reload failed (may not exist anymore): {blob.name} | {e}"
                log(msg)
                result["errors"].append({"name": blob.name, "generation": None, "error": msg})
                continue

            generation = int(blob.generation) if blob.generation is not None else None

            if already_done(blob.name, generation):
                log(f"Skipping duplicate (already done): {blob.name} gen={generation}")
                result["skipped"].append({"name": blob.name, "generation": generation, "reason": "already_done"})
                continue

            if not acquire_lock(blob.name, generation):
                log(f"Skipping duplicate (lock exists): {blob.name} gen={generation}")
                result["skipped"].append({"name": blob.name, "generation": generation, "reason": "lock_exists"})
                continue

            if not blob.exists():
                log(f"Blob no longer exists in source bucket; skipping: {blob.name}")
                result["skipped"].append({"name": blob.name, "generation": generation, "reason": "missing_in_source"})
                continue

            with tempfile.TemporaryDirectory() as tmpdir:
                local_xlsx = os.path.join(tmpdir, "file.xlsx")
                blob.download_to_filename(local_xlsx)

                df = read_xlsx(local_xlsx)
                df, col_map = normalize_and_clean_df(df)

                if i == 0:
                    ensure_table_exists(table_ref, df)

                job = bq_client.load_table_from_dataframe(
                    df,
                    table_ref,
                    job_config=bigquery.LoadJobConfig(
                        write_disposition="WRITE_APPEND",
                        schema_update_options=["ALLOW_FIELD_ADDITION"],
                    )
                )
                job.result()

                upload_sidecar(blob.name, col_map)
                move_blob_to_archive(blob.name)

                result["did_work"] = True
                result["processed"].append({"name": blob.name, "generation": generation})
                log(f"GCS→BQ complete (not marked done yet): {blob.name} gen={generation}")

        return result

    except Exception:
        msg = traceback.format_exc()
        log(msg)
        result["status"] = "error"
        result["errors"].append({"name": blob_name, "generation": None, "error": msg})
        return result
