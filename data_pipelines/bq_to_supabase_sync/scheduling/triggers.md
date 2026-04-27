# Scheduling & Triggers

One trigger mechanism keeps the sync running automatically.

---

## Cloud Scheduler — BigQuery-to-Supabase Poller

**Type:** Time-based (cron)
**Schedule:** `0 1,7,13,19 * * *` (four times daily — 1am, 7am, 1pm, 7pm)
**Timezone:** America/Chicago
**Region:** us-west1
**HTTP method:** GET

| Job name | Target service |
|---|---|
| `replicate-prod-tables-to-supabase-v2-scheduled` | `replicate-prod-tables-to-supabase-v2` |

The job hits the service's HTTP endpoint, which acquires an in-process lock and runs a full sync of all five tables sequentially. If the service is already mid-sync when the next invocation fires, it returns `{"status": "skipped"}` immediately — no queuing, no duplicate runs.

**Why four times daily?** The upstream pitchbook CRM pipeline runs ad-hoc throughout the day. Syncing every six hours keeps the Supabase replica fresh enough for downstream consumers (dashboards, APIs) without hammering BigQuery or holding a long-lived Postgres connection more than necessary.

---

## End-to-End Flow

```
Cloud Scheduler fires (1am / 7am / 1pm / 7pm CT)
  → HTTP GET → replicate-prod-tables-to-supabase-v2
    → acquire in-process lock (skip if already running)
      → for each table (companies, deals, investors, signal_investors, g1_signal_investors):
          → fetch schema from BigQuery
          → CREATE TABLE IF NOT EXISTS in Supabase (auto-migrate new columns)
          → SELECT * FROM Prod.* in BigQuery
          → batch upsert into Supabase via ON CONFLICT DO UPDATE
          → DELETE stale rows no longer present in BigQuery
      → release lock → return JSON results summary
```
