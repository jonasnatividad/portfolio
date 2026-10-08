-- Self-contained tests. Paste into the BigQuery console and run; no tables
-- are needed and the query scans 0 bytes. Uses TEMP copies of the helper
-- functions so it runs before 01_functions.sql is deployed.
--
-- US DST dates used (America/New_York):
--   2026-03-08  spring forward: 02:00 EST -> 03:00 EDT (02:00-02:59 does not exist)
--   2026-11-01  fall back:      02:00 EDT -> 01:00 EST (01:00-01:59 happens twice)

CREATE TEMP FUNCTION tz_offset_minutes(ts TIMESTAMP, tz STRING) AS (
  DATETIME_DIFF(DATETIME(ts, tz), DATETIME(ts, 'UTC'), MINUTE)
);

CREATE TEMP FUNCTION local_to_utc(local_dt DATETIME, tz STRING) AS ((
  SELECT
    CASE
      WHEN DATETIME(c_before, tz) = local_dt AND DATETIME(c_after, tz) = local_dt THEN LEAST(c_before, c_after)
      WHEN DATETIME(c_before, tz) = local_dt THEN c_before
      WHEN DATETIME(c_after, tz) = local_dt THEN c_after
      ELSE c_before
    END
  FROM (
    SELECT
      TIMESTAMP_SUB(naive, INTERVAL tz_offset_minutes(TIMESTAMP_SUB(naive, INTERVAL 1 DAY), tz) MINUTE) AS c_before,
      TIMESTAMP_SUB(naive, INTERVAL tz_offset_minutes(TIMESTAMP_ADD(naive, INTERVAL 1 DAY), tz) MINUTE) AS c_after
    FROM (SELECT TIMESTAMP(local_dt, 'UTC') AS naive)
  )
));

CREATE TEMP FUNCTION next_run_utc(now_ts TIMESTAMP, local_time TIME, tz STRING) AS ((
  SELECT IF(today_run > now_ts, today_run,
            local_to_utc(DATETIME(DATE_ADD(local_today, INTERVAL 1 DAY), local_time), tz))
  FROM (
    SELECT local_today, local_to_utc(DATETIME(local_today, local_time), tz) AS today_run
    FROM (SELECT DATE(now_ts, tz) AS local_today)
  )
));

WITH cases AS (
  SELECT * FROM UNNEST([
    -- A daily 06:00 job: the UTC hour moves by one across each transition.
    STRUCT('day before spring forward, 06:00' AS name, DATETIME '2026-03-07 06:00:00' AS local_dt, TIMESTAMP '2026-03-07 11:00:00+00' AS expected),
    STRUCT('spring forward day, 06:00',          DATETIME '2026-03-08 06:00:00', TIMESTAMP '2026-03-08 10:00:00+00'),
    STRUCT('day before fall back, 06:00',        DATETIME '2026-10-31 06:00:00', TIMESTAMP '2026-10-31 10:00:00+00'),
    STRUCT('fall back day, 06:00',               DATETIME '2026-11-01 06:00:00', TIMESTAMP '2026-11-01 11:00:00+00'),
    -- Edge cases inside the transition hour.
    STRUCT('non-existent 02:30 shifts to 03:30 EDT', DATETIME '2026-03-08 02:30:00', TIMESTAMP '2026-03-08 07:30:00+00'),
    STRUCT('ambiguous 01:30 takes first (EDT)',      DATETIME '2026-11-01 01:30:00', TIMESTAMP '2026-11-01 05:30:00+00'),
    -- Local midnight boundaries: the two transition days are 23 and 25 hours long.
    STRUCT('midnight starting spring forward day', DATETIME '2026-03-08 00:00:00', TIMESTAMP '2026-03-08 05:00:00+00'),
    STRUCT('midnight after spring forward day',    DATETIME '2026-03-09 00:00:00', TIMESTAMP '2026-03-09 04:00:00+00'),
    STRUCT('midnight starting fall back day',      DATETIME '2026-11-01 00:00:00', TIMESTAMP '2026-11-01 04:00:00+00'),
    STRUCT('midnight after fall back day',         DATETIME '2026-11-02 00:00:00', TIMESTAMP '2026-11-02 05:00:00+00')
  ])
),
next_run_cases AS (
  SELECT * FROM UNNEST([
    -- Called at 10:30 UTC on spring forward day = 06:30 EDT, so today's run has passed.
    STRUCT('next run after spring forward run' AS name, TIMESTAMP '2026-03-08 10:30:00+00' AS now_ts, TIMESTAMP '2026-03-09 10:00:00+00' AS expected),
    -- Called at 10:30 UTC on fall back day = 05:30 EST, so today's run is still ahead at 11:00 UTC.
    STRUCT('next run on fall back morning',      TIMESTAMP '2026-11-01 10:30:00+00', TIMESTAMP '2026-11-01 11:00:00+00'),
    -- Called late evening local time, which is already the next UTC date.
    STRUCT('late evening, UTC date already ahead', TIMESTAMP '2026-07-15 03:00:00+00', TIMESTAMP '2026-07-15 10:00:00+00')
  ])
),
results AS (
  SELECT name, local_to_utc(local_dt, 'America/New_York') AS actual, expected FROM cases
  UNION ALL
  SELECT name, next_run_utc(now_ts, TIME '06:00:00', 'America/New_York'), expected FROM next_run_cases
)
SELECT
  name,
  actual,
  expected,
  IF(actual = expected, 'PASS', 'FAIL') AS result
FROM results
ORDER BY result, name;

-- Hard failure (for CI): uncomment to make the script error on any mismatch.
-- ASSERT local_to_utc(DATETIME '2026-11-01 01:30:00', 'America/New_York') = TIMESTAMP '2026-11-01 05:30:00+00'
--   AS 'ambiguous fall-back time should resolve to the first occurrence';
-- ASSERT local_to_utc(DATETIME '2026-03-08 02:30:00', 'America/New_York') = TIMESTAMP '2026-03-08 07:30:00+00'
--   AS 'non-existent spring-forward time should shift forward by the gap';
