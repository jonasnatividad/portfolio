-- PROD layer: one row per sales rep for the weekly team sheet.
CREATE OR REPLACE VIEW `your-gcp-project.sales_prod.rep_scorecard` AS
SELECT
  owner                                                     AS rep,
  COUNTIF(NOT is_closed)                                    AS open_deals,
  SUM(IF(NOT is_closed, amount_usd, 0))                     AS open_pipeline_usd,
  SUM(IF(NOT is_closed, weighted_amount_usd, 0))            AS weighted_pipeline_usd,
  COUNTIF(is_won)                                           AS won_deals,
  SUM(IF(is_won, amount_usd, 0))                            AS won_amount_usd,
  SAFE_DIVIDE(COUNTIF(is_won), COUNTIF(is_closed))          AS win_rate,
  COUNTIF(is_overdue)                                       AS overdue_deals
FROM `your-gcp-project.sales_live.deal_pipeline`
GROUP BY rep
ORDER BY weighted_pipeline_usd DESC;
