-- Run guard: decides whether the daily job should run NOW, and records the run.
--
-- Deployment: trigger this script every hour, on the hour, in UTC
-- (BigQuery scheduled query "every 1 hours", or Cloud Scheduler with
-- time zone "Etc/UTC"). It does real work only once per local day:
--
--   * at or after the target local time (06:00 America/New_York),
--   * within a 3-hour catch-up window (covers a missed or delayed trigger),
--   * and only if no successful run is recorded for that local date.
--
-- Because the guard is keyed on the LOCAL date, a DST change can never cause
-- a double run (fall back) or a skipped run (spring forward).

-- One-time setup:
-- CREATE TABLE IF NOT EXISTS `your-gcp-project.ops.job_runs` (
--   job_name     STRING NOT NULL,
--   run_date     DATE NOT NULL,      -- local business date the run covers
--   scheduled_at TIMESTAMP NOT NULL, -- target instant in UTC
--   started_at   TIMESTAMP NOT NULL,
--   status       STRING NOT NULL     -- 'running' | 'success' | 'failed'
-- );

DECLARE v_job_name STRING DEFAULT 'daily_sales_rollup';
DECLARE v_tz STRING DEFAULT 'America/New_York';
DECLARE v_local_run_time TIME DEFAULT TIME '06:00:00';
DECLARE v_catch_up_window INT64 DEFAULT 180;  -- minutes

DECLARE v_now_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP();
DECLARE v_local_date DATE DEFAULT DATE(v_now_ts, v_tz);
DECLARE v_scheduled_at TIMESTAMP DEFAULT `your-gcp-project.ops.local_to_utc`(DATETIME(v_local_date, v_local_run_time), v_tz);
DECLARE v_already_ran BOOL;

SET v_already_ran = EXISTS (
  SELECT 1
  FROM `your-gcp-project.ops.job_runs` AS r
  WHERE r.job_name = v_job_name
    AND r.run_date = v_local_date
    AND r.status IN ('running', 'success')
);

IF v_now_ts < v_scheduled_at
   OR v_now_ts >= TIMESTAMP_ADD(v_scheduled_at, INTERVAL v_catch_up_window MINUTE)
   OR v_already_ran THEN
  SELECT
    'skip' AS decision,
    v_local_date AS local_date,
    v_scheduled_at AS scheduled_at,
    `your-gcp-project.ops.next_run_utc`(v_now_ts, v_local_run_time, v_tz) AS next_run_utc,
    v_already_ran AS already_ran;
  RETURN;
END IF;

-- Claim the run first so an overlapping trigger cannot start a second copy.
INSERT INTO `your-gcp-project.ops.job_runs` (job_name, run_date, scheduled_at, started_at, status)
VALUES (v_job_name, v_local_date, v_scheduled_at, v_now_ts, 'running');

BEGIN
  -- The actual job. It is written to be idempotent for one local date:
  -- delete-then-insert the partition for "yesterday" in local time.
  DELETE FROM `your-gcp-project.reporting.daily_sales`
  WHERE sales_date = DATE_SUB(v_local_date, INTERVAL 1 DAY);

  INSERT INTO `your-gcp-project.reporting.daily_sales` (sales_date, orders, net_revenue)
  SELECT
    DATE(oi.created_at, v_tz) AS sales_date,
    COUNT(DISTINCT oi.order_id) AS orders,
    SUM(IF(oi.status NOT IN ('Cancelled', 'Returned'), oi.sale_price, 0)) AS net_revenue
  FROM `bigquery-public-data.thelook_ecommerce.order_items` AS oi
  -- The local day [00:00, 24:00) is 23, 24 or 25 hours long in UTC;
  -- converting both edges with local_to_utc gets that right automatically.
  WHERE oi.created_at >= `your-gcp-project.ops.local_to_utc`(DATETIME(DATE_SUB(v_local_date, INTERVAL 1 DAY), TIME '00:00:00'), v_tz)
    AND oi.created_at <  `your-gcp-project.ops.local_to_utc`(DATETIME(v_local_date, TIME '00:00:00'), v_tz)
  GROUP BY sales_date;

  UPDATE `your-gcp-project.ops.job_runs` AS r
  SET status = 'success'
  WHERE r.job_name = v_job_name AND r.run_date = v_local_date AND r.status = 'running';

EXCEPTION WHEN ERROR THEN
  UPDATE `your-gcp-project.ops.job_runs` AS r
  SET status = 'failed'
  WHERE r.job_name = v_job_name AND r.run_date = v_local_date AND r.status = 'running';
  RAISE USING MESSAGE = @@error.message;
END;
