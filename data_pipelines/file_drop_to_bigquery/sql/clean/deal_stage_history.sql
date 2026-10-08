-- CLEAN layer: every distinct stage a deal has been in, with when it was
-- first seen. Built from the daily snapshots, so the history exists even
-- though the CRM export only carries the current stage.
CREATE OR REPLACE VIEW `your-gcp-project.sales_clean.deal_stage_history` AS
SELECT
  NULLIF(TRIM(deal_id), '')                         AS deal_id,
  INITCAP(REGEXP_REPLACE(TRIM(stage), r'\s+', ' ')) AS stage,
  MIN(_file_date)                                   AS first_seen_date,
  MAX(_file_date)                                   AS last_seen_date
FROM `your-gcp-project.sales_raw.deals`
WHERE NULLIF(TRIM(deal_id), '') IS NOT NULL
GROUP BY 1, 2;
