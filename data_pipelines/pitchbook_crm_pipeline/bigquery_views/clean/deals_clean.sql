-- View: Pitchbook.clean.deals_clean
-- Casts all numeric/timestamp fields from raw STRING ingestion,
-- strips PitchBook copyright footer rows, and deduplicates by
-- deal_id keeping the most recent ingestion.

SELECT
  deal_id AS deal_id,
  companies AS companies,
  SAFE_CAST(deal_date AS TIMESTAMP) AS deal_date,
  SAFE_CAST(deal_size AS FLOAT64) AS deal_size,
  SAFE_CAST(post_valuation AS FLOAT64) AS post_valuation,
  deal_type AS deal_type,
  deal_type_2 AS deal_type_2,
  deal_type_3 AS deal_type_3,
  SAFE_CAST(deal_no AS FLOAT64) AS deal_no,
  deal_class AS deal_class,
  lead_sole_investors AS lead_sole_investors,
  follow_on_investors AS follow_on_investors,
  new_investors AS new_investors,
  investors AS investors,
  deal_synopsis AS deal_synopsis,
  acquired AS acquired,
  SAFE_CAST(pre_money_valuation AS FLOAT64) AS pre_money_valuation,
  SAFE_CAST(number_follow_on_investors AS FLOAT64) AS number_follow_on_investors,
  SAFE_CAST(number_new_investors AS FLOAT64) AS number_new_investors,
  investors_websites AS investors_websites,
  SAFE_CAST(number_investors AS FLOAT64) AS number_investors,
  SAFE_CAST(employees AS FLOAT64) AS employees,
  deal_status AS deal_status,
  SAFE_CAST(price_per_share AS FLOAT64) AS price_per_share,
  vc_round_up_down_flat AS vc_round_up_down_flat,
  vc_round AS vc_round,
  SAFE_CAST(time_between_vc_rounds AS FLOAT64) AS time_between_vc_rounds,
  SAFE_CAST(valuation_step_up AS FLOAT64) AS valuation_step_up,
  post_valuation_status AS post_valuation_status,
  SAFE_CAST(raised_to_date AS FLOAT64) AS raised_to_date,
  series AS series,
  company_id AS company_id,
  view_company_online AS view_company_online,
  ingested_at AS ingested_at
FROM `your-project-id.Pitchbook_raw.deals_raw`
WHERE deal_id NOT LIKE "%© PitchBook Data, Inc.%"
QUALIFY ROW_NUMBER() OVER (PARTITION BY deal_id ORDER BY ingested_at DESC) = 1;
