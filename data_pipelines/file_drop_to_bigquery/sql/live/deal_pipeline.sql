-- LIVE layer: business logic on top of clean data. Always current; this is
-- where definitions live (stage order, win probability, weighted pipeline,
-- overdue flag). Analysts query live views while building; dashboards use prod.
CREATE OR REPLACE VIEW `your-gcp-project.sales_live.deal_pipeline` AS
WITH stage_rules AS (
  SELECT * FROM UNNEST([
    STRUCT('Prospecting' AS stage, 1 AS stage_order, 0.10 AS win_probability),
    STRUCT('Discovery',   2, 0.20),
    STRUCT('Proposal',    3, 0.40),
    STRUCT('Negotiation', 4, 0.70),
    STRUCT('Closed Won',  5, 1.00),
    STRUCT('Closed Lost', 6, 0.00)
  ])
),
stage_entered AS (
  SELECT deal_id, stage, first_seen_date AS stage_entered_date
  FROM `your-gcp-project.sales_clean.deal_stage_history`
)
SELECT
  d.deal_id,
  d.deal_name,
  d.company_id,
  c.company_name,
  c.industry,
  c.employee_band,
  c.country_code,
  d.plan,
  d.stage,
  COALESCE(r.stage_order, 99)                      AS stage_order,
  r.stage IS NULL                                  AS is_unknown_stage,
  d.owner,
  d.amount_usd,
  ROUND(d.amount_usd * COALESCE(r.win_probability, 0), 2) AS weighted_amount_usd,
  d.created_date,
  d.expected_close_date,
  DATE_TRUNC(d.expected_close_date, MONTH)         AS expected_close_month,
  d.is_closed,
  d.is_won,
  d.is_missing_amount,
  NOT d.is_closed AND d.expected_close_date < CURRENT_DATE() AS is_overdue,
  DATE_DIFF(CURRENT_DATE(), d.created_date, DAY)   AS deal_age_days,
  DATE_DIFF(CURRENT_DATE(), COALESCE(s.stage_entered_date, d.created_date), DAY) AS days_in_stage,
  d.last_updated_at,
  d._source_file                                   AS latest_source_file
FROM `your-gcp-project.sales_clean.deals` AS d
LEFT JOIN `your-gcp-project.sales_clean.companies` AS c USING (company_id)
LEFT JOIN stage_rules AS r ON r.stage = d.stage
LEFT JOIN stage_entered AS s ON s.deal_id = d.deal_id AND s.stage = d.stage;
