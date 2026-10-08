-- Persistent helper functions for running jobs at a fixed LOCAL wall-clock time.
-- Create once in a utility dataset, e.g. `your-gcp-project.ops`.
--
-- Core idea: never hard-code a UTC hour. Store the schedule as
-- (local time, IANA time zone) and convert to UTC for each specific date,
-- because the UTC offset of America/New_York is -05:00 in winter and -04:00
-- in summer.

-- Offset of a time zone from UTC, in minutes, at a given instant.
-- Example: tz_offset_minutes(TIMESTAMP '2026-07-01 12:00:00+00', 'America/New_York') = -240
CREATE OR REPLACE FUNCTION `your-gcp-project.ops.tz_offset_minutes`(ts TIMESTAMP, tz STRING)
RETURNS INT64
AS (
  DATETIME_DIFF(DATETIME(ts, tz), DATETIME(ts, 'UTC'), MINUTE)
);

-- Convert a local wall-clock DATETIME in zone `tz` to a UTC TIMESTAMP,
-- with an explicit, documented policy for the two DST edge cases:
--
--   * Ambiguous time (fall back, e.g. 01:30 happens twice):
--       choose the FIRST occurrence (the earlier UTC instant).
--   * Non-existent time (spring forward, e.g. 02:30 never happens):
--       shift forward by the length of the gap (02:30 -> 03:30 local),
--       i.e. interpret it with the offset that applied before the change.
--
-- Method: try the offset in effect one day before and one day after the
-- local time. A candidate is valid if converting it back to local time
-- gives the wall-clock time we asked for. (Assumes at most one offset change
-- within +/- 1 day, which holds for every real IANA zone.)
CREATE OR REPLACE FUNCTION `your-gcp-project.ops.local_to_utc`(local_dt DATETIME, tz STRING)
RETURNS TIMESTAMP
AS ((
  SELECT
    CASE
      WHEN DATETIME(c_before, tz) = local_dt AND DATETIME(c_after, tz) = local_dt
        THEN LEAST(c_before, c_after)          -- ambiguous: first occurrence
      WHEN DATETIME(c_before, tz) = local_dt THEN c_before
      WHEN DATETIME(c_after, tz) = local_dt THEN c_after
      ELSE c_before                            -- gap: shift forward
    END
  FROM (
    SELECT
      TIMESTAMP_SUB(naive, INTERVAL `your-gcp-project.ops.tz_offset_minutes`(TIMESTAMP_SUB(naive, INTERVAL 1 DAY), tz) MINUTE) AS c_before,
      TIMESTAMP_SUB(naive, INTERVAL `your-gcp-project.ops.tz_offset_minutes`(TIMESTAMP_ADD(naive, INTERVAL 1 DAY), tz) MINUTE) AS c_after
    FROM (SELECT TIMESTAMP(local_dt, 'UTC') AS naive)
  )
));

-- The UTC instant of the next scheduled run strictly after `now_ts`
-- for a job that runs daily at `local_time` in zone `tz`.
CREATE OR REPLACE FUNCTION `your-gcp-project.ops.next_run_utc`(now_ts TIMESTAMP, local_time TIME, tz STRING)
RETURNS TIMESTAMP
AS ((
  SELECT
    IF(
      today_run > now_ts,
      today_run,
      `your-gcp-project.ops.local_to_utc`(DATETIME(DATE_ADD(local_today, INTERVAL 1 DAY), local_time), tz)
    )
  FROM (
    SELECT
      local_today,
      `your-gcp-project.ops.local_to_utc`(DATETIME(local_today, local_time), tz) AS today_run
    FROM (SELECT DATE(now_ts, tz) AS local_today)
  )
));
