-- PROD layer: stable reporting contract. Column names and grain here only
-- change with a version bump, because sheets and dashboards depend on them.
-- Prod views select from live views only, never from raw or clean.
CREATE OR REPLACE VIEW `your-gcp-project.sales_prod.pipeline_by_stage` AS
SELECT
  stage,
  stage_order,
  COUNT(*)                          AS deals,
  SUM(amount_usd)                   AS amount_usd,
  SUM(weighted_amount_usd)          AS weighted_amount_usd,
  COUNTIF(is_overdue)               AS overdue_deals,
  ROUND(AVG(days_in_stage), 1)      AS avg_days_in_stage
FROM `your-gcp-project.sales_live.deal_pipeline`
WHERE NOT is_closed
GROUP BY stage, stage_order
ORDER BY stage_order;
