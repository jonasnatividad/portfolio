# Scheduling & Triggers

Two trigger mechanisms keep the pipeline running automatically.

---

## 1. Cloud Scheduler — Drive-to-GCS Poller

**Type:** Time-based (cron)
**Schedule:** `* * * * *` (every minute)
**Timezone:** America/New_York
**Region:** us-central1
**HTTP method:** GET

Each job invokes its corresponding Cloud Run service, which scans a watched Google Drive folder for new `.xlsx` exports, uploads them to the GCS landing bucket, and deletes the originals from Drive.

| Job name | Target service |
|---|---|
| `process-companies-drive-scheduled` | `process-companies-drive` |
| `process-deals-drive-scheduled` | `process-deals-drive` |
| `process-investors-drive-scheduled` | `process-investors-drive` |
| `process-signal-investors-drive-scheduled` | `process-signal-investors-drive` |

**Why every minute?** The UI Vision automation runs on an ad-hoc schedule. A 1-minute poll ensures files land in GCS within 60 seconds of the export completing, keeping end-to-end latency low without requiring a push notification from Drive.

The services themselves are idempotent — if no new file is present in Drive, the invocation is a no-op.

---

## 2. GCS Object Finalize — Bucket-to-BigQuery Trigger

**Type:** Event-driven (Eventarc — GCS Pub/Sub notification)
**Event:** `google.storage.object.finalize` (fires when a new object is fully written to a bucket)
**Region:** us-central1

Each GCS landing bucket has an Eventarc trigger bound to its corresponding `process-*-bucket` Cloud Run service. When the Drive poller drops a new `.xlsx` into a landing bucket, GCS emits a finalize event → Eventarc delivers it to Cloud Run → the service processes it immediately.

| Landing bucket | Eventarc trigger target |
|---|---|
| `pitchbook-companies-landing` | `process-companies-bucket` |
| `pitchbook-deals-landing` | `process-deals-bucket` |
| `pitchbook-investors-landing` | `process-investors-bucket` |
| `pitchbook-signal-investors-landing` | `process-signal-investors-bucket` |

The triggered service:
1. Acquires a generation-matched GCS lock to prevent duplicate processing
2. Downloads the `.xlsx` from the landing bucket
3. Normalizes column names and strips PitchBook's multi-row header
4. Appends cleaned rows to the BigQuery raw table
5. Archives the source file and writes a DONE marker to GCS
6. Runs the Grist refresh (BigQuery live view → Grist incremental sync)

**Why event-driven instead of polling?** Eliminates polling latency and wasted invocations — the service only runs when there is actually a file to process.

---

## End-to-End Flow

```
UI Vision export runs (manual or local schedule)
  → .xlsx file lands in Google Drive folder
    → Cloud Scheduler fires (within 60s)
      → process-*-drive service uploads file to GCS landing bucket
        → GCS object.finalize event fires (within seconds)
          → Eventarc invokes process-*-bucket service
            → XLSX → BigQuery raw append
            → BigQuery views recompute (clean → prod → live)
            → Grist CRM refreshed from live view
            → Custom Grist fields written back to App.overlay_* in BigQuery
```
