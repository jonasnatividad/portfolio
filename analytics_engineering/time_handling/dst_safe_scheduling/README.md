# DST-Safe Daily Scheduling in BigQuery

How to run a daily job at a fixed **local** time (06:00 in `America/New_York`) when the
scheduler, the warehouse and the data all live in UTC, without the job drifting by an
hour, running twice, or being skipped when daylight saving time starts or ends.

## The problem

New York is UTC-5 in winter and UTC-4 in summer. A cron entry of `0 11 * * *` in UTC
fires at 06:00 local in winter but at 07:00 local all summer. Two less obvious bugs
follow from the same root cause:

- **Daily windows are not 24 hours.** The local day that contains the spring-forward
  change is 23 hours long and the fall-back day is 25 hours. `created_at >= day_start
  AND created_at < day_start + INTERVAL 24 HOUR` silently drops or double-counts an hour.
- **Wall-clock gaps and overlaps.** On spring-forward day 02:30 never happens; on
  fall-back day 01:30 happens twice. A schedule set inside that hour needs a rule.

## The approach

1. **Store the schedule as local time + IANA zone**, never as a UTC hour.
2. **Convert to UTC per date** with `local_to_utc(DATETIME, tz)`, which applies an explicit
   policy for the edge cases:
   - ambiguous time: use the first occurrence;
   - non-existent time: shift forward by the gap (02:30 becomes 03:30 local).

   It works by trying the UTC offset in force one day before and one day after, then
   keeping the candidate that converts back to the requested wall-clock time.
3. **Trigger hourly in UTC and let a guard decide.** The guard (`02_run_guard.sql`) runs
   the job only if the current time is inside `[scheduled_at, scheduled_at + 3h)` and no
   run is recorded for the **local date**. Keying on the local date makes the job
   idempotent: an extra trigger, a retry or the repeated hour on fall-back day cannot
   start a second run, and the catch-up window covers a delayed trigger.
4. **Claim, run, mark.** The run is recorded as `running` before the work starts, then
   set to `success` or `failed`. The job itself is delete-then-insert for one local date,
   so a manual re-run after a failure is safe.
5. **Build local-day windows from two converted midnights**, so a day is automatically
   23, 24 or 25 hours long in UTC.

## Files

| File | What it does |
|---|---|
| `sql/01_functions.sql` | Persistent UDFs: `tz_offset_minutes`, `local_to_utc`, `next_run_utc` |
| `sql/02_run_guard.sql` | Hourly script: decide, claim the run, do the work, record the outcome |
| `sql/03_tests.sql` | Self-contained tests (temp functions, 0 bytes scanned) |

## Tests

`03_tests.sql` covers the two 2026 US transition days:

| Case | Local | Expected UTC |
|---|---|---|
| Day before spring forward, 06:00 | 2026-03-07 06:00 EST | 11:00 |
| Spring forward day, 06:00 | 2026-03-08 06:00 EDT | 10:00 |
| Day before fall back, 06:00 | 2026-10-31 06:00 EDT | 10:00 |
| Fall back day, 06:00 | 2026-11-01 06:00 EST | 11:00 |
| Non-existent 02:30 | 2026-03-08 | 07:30 (03:30 EDT) |
| Ambiguous 01:30 | 2026-11-01 | 05:30 (first, EDT) |
| Local midnights around both changes | | 23-hour and 25-hour days |
| `next_run_utc` before/after today's run | | today or tomorrow |

All 13 cases pass in BigQuery.

## Deploying

1. Replace `your-gcp-project` and run `sql/01_functions.sql` once.
2. Create the `ops.job_runs` table (DDL is at the top of `02_run_guard.sql`) and the
   target table `reporting.daily_sales (sales_date DATE, orders INT64, net_revenue NUMERIC)`.
3. Schedule `02_run_guard.sql` as a BigQuery scheduled query repeating **every 1 hour**,
   or call it from Cloud Scheduler with time zone `Etc/UTC` and cron `0 * * * *`.
   Running hourly costs almost nothing: on 23 of 24 triggers the guard exits after one
   tiny lookup.

**Simpler alternative when the scheduler supports time zones:** Cloud Scheduler accepts
`timeZone: America/New_York` and handles DST itself. The guard is still worth keeping,
because it gives idempotency, a run log and catch-up after a missed trigger, and the
window logic in step 5 is needed either way.
