-- Blocking data quality checks as a BigQuery script that fails loudly.
-- Schedule it as a BigQuery scheduled query (daily, after the expected export
-- time) with failure emails turned on: if any blocking check fails, the run
-- errors and the team gets an email, even on days nobody opens the sheet.
--   bq query --project_id=your-gcp-project --use_legacy_sql=false < sql/checks/assertions.sql

ASSERT (
  SELECT COUNT(*)
  FROM `your-gcp-project.sales_live.data_quality`
  WHERE severity = 'block' AND failing_rows > 0
) = 0 AS 'Blocking data quality check failed: query sales_live.data_quality for details';

-- The clean layer must hold exactly one row per id; more means deduplication broke.
ASSERT (
  SELECT COUNT(*) - COUNT(DISTINCT deal_id) FROM `your-gcp-project.sales_clean.deals`
) = 0 AS 'sales_clean.deals has repeated deal_id values';

ASSERT (
  SELECT COUNT(*) - COUNT(DISTINCT company_id) FROM `your-gcp-project.sales_clean.companies`
) = 0 AS 'sales_clean.companies has repeated company_id values';

SELECT 'all blocking checks passed' AS result;
