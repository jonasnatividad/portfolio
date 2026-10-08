-- PROD layer: expected bookings by close month, open deals only, next 6 months.
CREATE OR REPLACE VIEW `your-gcp-project.sales_prod.forecast_by_month` AS
SELECT
  expected_close_month,
  plan,
  COUNT(*)                   AS deals,
  SUM(amount_usd)            AS amount_usd,
  SUM(weighted_amount_usd)   AS weighted_amount_usd
FROM `your-gcp-project.sales_live.deal_pipeline`
WHERE NOT is_closed
  AND expected_close_month BETWEEN DATE_TRUNC(CURRENT_DATE(), MONTH)
                               AND DATE_ADD(DATE_TRUNC(CURRENT_DATE(), MONTH), INTERVAL 5 MONTH)
GROUP BY expected_close_month, plan
ORDER BY expected_close_month, plan;
