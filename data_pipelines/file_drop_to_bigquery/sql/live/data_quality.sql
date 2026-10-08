-- LIVE layer: data quality checks the sheet refresh reads before publishing.
-- One row per check; the refresh service refuses to publish if any check with
-- severity = 'block' fails.
CREATE OR REPLACE VIEW `your-gcp-project.sales_live.data_quality` AS
SELECT 'deals_without_company' AS check_name, 'block' AS severity,
       COUNT(*) AS failing_rows
FROM `your-gcp-project.sales_live.deal_pipeline`
WHERE company_name IS NULL
UNION ALL
SELECT 'unknown_stage', 'block', COUNTIF(is_unknown_stage)
FROM `your-gcp-project.sales_live.deal_pipeline`
UNION ALL
SELECT 'missing_amount', 'warn', COUNTIF(is_missing_amount)
FROM `your-gcp-project.sales_live.deal_pipeline`
UNION ALL
SELECT 'stale_data', 'block',
       IF(MAX(_loaded_at) < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 36 HOUR), 1, 0)
FROM `your-gcp-project.sales_raw.deals`;
