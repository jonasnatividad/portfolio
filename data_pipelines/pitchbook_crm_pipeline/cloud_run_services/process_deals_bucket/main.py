import os
import logging
import traceback
from typing import Any, Dict

import functions_framework
from cloudevents.http import CloudEvent
from google.cloud import storage

from deals_gcs_to_bq import process_files, mark_done, already_done
import deals_grist_refresh as grist_refresh

SOURCE_BUCKET  = os.environ.get("SOURCE_BUCKET",  "pitchbook-deals")
ARCHIVE_BUCKET = os.environ.get("ARCHIVE_BUCKET", "pitchbook-deals-archive")

storage_client = storage.Client()

def _exists(bucket: str, name: str) -> bool:
    return storage_client.bucket(bucket).blob(name).exists()

def _is_interesting_object(name: str) -> bool:
    if not name or name.endswith("/"):
        return False
    base = name.rsplit("/", 1)[-1]
    if base.startswith(".") or base.startswith("_"):
        return False
    return name.lower().endswith(".xlsx")

@functions_framework.cloud_event
def handle_gcs(event: CloudEvent):
    data: Dict[str, Any] = event.data or {}
    bucket  = data.get("bucket")
    name    = data.get("name")
    gen_raw = data.get("generation")

    try:
        gen = int(gen_raw) if gen_raw is not None else None
    except Exception:
        gen = None

    try:
        logging.info(f"event-id={event['id']} type={event['type']} subject={event['subject']}")
    except Exception:
        pass
    logging.info(f"GCS event: bucket={bucket} name={name} generation={gen_raw}")

    if bucket != SOURCE_BUCKET:
        logging.info(f"Ignoring event from unexpected bucket: {bucket!r}")
        return ("ok", 200)

    if not _is_interesting_object(name):
        logging.info(f"Ignoring non-target object: {name!r}")
        return ("ok", 200)

    # Fast-path: already fully processed
    if already_done(name, gen):
        logging.info(f"Already done: {name} gen={gen}")
        return ("ok", 200)

    # Visibility guard: catch duplicate events where source was already archived
    in_source  = _exists(SOURCE_BUCKET, name)
    in_archive = _exists(ARCHIVE_BUCKET, name)

    if not in_source and in_archive:
        logging.info(f"Already archived: {name}. Skipping.")
        return ("ok", 200)

    if not in_source and not in_archive:
        logging.warning(f"Object {name} not found in source or archive. Skipping.")
        return ("ok", 200)

    # -------- 1. GCS → BigQuery + archive --------
    result = process_files(blob_name=name)
    logging.info(f"GCS→BQ result: {result}")

    if result.get("status") == "error":
        # Another invocation may have raced and already archived it — treat as harmless
        if not _exists(SOURCE_BUCKET, name) and _exists(ARCHIVE_BUCKET, name):
            logging.info(f"Post-error archive detected for {name}; treating as processed.")
            return ("ok", 200)
        raise RuntimeError(f"gcs_to_bq failed for {name}: {result}")

    if not result.get("did_work"):
        logging.info(f"No work performed for {name} (duplicate/lock). Skipping Grist refresh.")
        return ("ok", 200)

    # -------- 2. Grist refresh --------
    try:
        grist_refresh.main()
    except Exception as e:
        logging.error(f"Grist refresh failed for {name}: {e}")
        logging.error(traceback.format_exc())
        # Return 200 to prevent Eventarc retrying the GCS event (would re-append data)
        return ("ok", 200)

    # -------- 3. Mark DONE only after Grist succeeds --------
    try:
        mark_done(name, gen)
        logging.info(f"Marked DONE: {name} gen={gen}")
    except Exception as e:
        logging.error(f"Failed to write DONE marker for {name} gen={gen}: {e}")
        logging.error(traceback.format_exc())
        return ("ok", 200)

    logging.info(f"Pipeline complete for {name}.")
    return ("ok", 200)
