-- View: Pitchbook.prod.investors_prod
-- Enriches investors_clean with deal-derived activity metrics computed
-- against deals_prod. A pre-aggregation CTE (investor_deal_metrics) handles
-- all per-investor counts to avoid repeated full-table scans.
--
-- Key computed fields:
--   max_fund_200m / max_fund_150m         — fund size eligibility flags
--   early_deals_L3Y                       — early stage deal activity (last 3 years)
--   upstream_qualifiers_L3Y / L5Y         — companies that later hit qualifying rounds
--   upstream_g1_qualifiers_L3Y / L5Y      — same, filtered to G1 signal-led deals
--   coinvests_signal_*/coinvests_g1_*     — co-investment overlap with signal lists
--   percent_signal_*/percent_g1_*         — overlap rates as a share of early deals
--   qualifying_deal_names                 — list of qualifying company names
--   last_qualifying_deal_date             — most recent qualifying deal date

WITH investor_deal_metrics AS (
  SELECT
    TRIM(investor_name) AS investor_name,

    COUNT(CASE
      WHEN stage_indicators LIKE '%Early%'
        AND DATE(deal_date) >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 YEAR)
      THEN 1
    END) AS early_deals_L3Y_count,

    COUNT(DISTINCT CASE
      WHEN upstream_qualifier = TRUE
        AND DATE(deal_date) >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 YEAR)
      THEN company_id
    END) AS upstream_qualifiers_L3Y_count,

    COUNT(DISTINCT CASE
      WHEN upstream_qualifier = TRUE
        AND DATE(deal_date) >= DATE_SUB(CURRENT_DATE(), INTERVAL 5 YEAR)
      THEN company_id
    END) AS upstream_qualifiers_L5Y_count,

    COUNT(DISTINCT CASE
      WHEN upstream_g1_qualifier = TRUE
        AND DATE(deal_date) >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 YEAR)
      THEN company_id
    END) AS upstream_g1_qualifiers_L3Y_count,

    COUNT(DISTINCT CASE
      WHEN upstream_g1_qualifier = TRUE
        AND DATE(deal_date) >= DATE_SUB(CURRENT_DATE(), INTERVAL 5 YEAR)
      THEN company_id
    END) AS upstream_g1_qualifiers_L5Y_count,

    COUNT(CASE
      WHEN signal_invested = TRUE
        AND stage_indicators LIKE '%Early%'
        AND DATE(deal_date) >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 YEAR)
      THEN 1
    END) AS coinvests_signal_inv_early_L3Y_count,

    COUNT(CASE
      WHEN g1_signal_invested = TRUE
        AND stage_indicators LIKE '%Early%'
        AND DATE(deal_date) >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 YEAR)
      THEN 1
    END) AS coinvests_g1_inv_early_L3Y_count,

    COUNT(CASE
      WHEN signal_led = TRUE
        AND stage_indicators LIKE '%Early%'
        AND DATE(deal_date) >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 YEAR)
      THEN 1
    END) AS coinvests_signal_led_early_L3Y_count,

    COUNT(CASE
      WHEN g1_signal_led = TRUE
        AND stage_indicators LIKE '%Early%'
        AND DATE(deal_date) >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 YEAR)
      THEN 1
    END) AS coinvests_g1_led_early_L3Y_count,

    STRING_AGG(
      CASE
        WHEN filter_qualification = 'Qualifies' AND investable_deal_type = TRUE
        THEN companies
      END,
      ', ' ORDER BY deal_date DESC
    ) AS qualifying_deal_names_list,

    MAX(CASE
      WHEN filter_qualification = 'Qualifies' AND investable_deal_type = TRUE
      THEN deal_date
    END) AS last_qualifying_deal_date_value

  FROM `your-project-id.Prod.deals_prod` d
  CROSS JOIN UNNEST(SPLIT(d.investors_firm_only, ',')) AS investor_name
  WHERE d.investors_firm_only IS NOT NULL
  GROUP BY TRIM(investor_name)
)

SELECT
  i.*,

  -- Field Name: max_fund_200m
  -- Summary: TRUE if max_fund_size <= 200M or is unknown
  (i.max_fund_size <= 200 OR i.max_fund_size IS NULL) AS max_fund_200m,

  -- Field Name: max_fund_150m
  -- Summary: TRUE if max_fund_size <= 150M or is unknown
  (i.max_fund_size <= 150 OR i.max_fund_size IS NULL) AS max_fund_150m,

  -- Field Name: early_deals_L3Y
  -- Summary: Count of early stage deals this investor participated in over the last 3 years
  IFNULL(m.early_deals_L3Y_count, 0) AS early_deals_L3Y,

  -- Field Name: upstream_qualifiers_L3Y
  -- Summary: Distinct companies this investor backed that later hit a qualifying round (last 3 years)
  IFNULL(m.upstream_qualifiers_L3Y_count, 0) AS upstream_qualifiers_L3Y,

  -- Field Name: upstream_qualifiers_L5Y
  -- Summary: Same as upstream_qualifiers_L3Y over a 5-year window
  IFNULL(m.upstream_qualifiers_L5Y_count, 0) AS upstream_qualifiers_L5Y,

  -- Field Name: upstream_g1_qualifiers_L3Y
  -- Summary: Distinct companies this investor backed that later hit a G1-signal-led qualifying round (last 3 years)
  IFNULL(m.upstream_g1_qualifiers_L3Y_count, 0) AS upstream_g1_qualifiers_L3Y,

  -- Field Name: upstream_g1_qualifiers_L5Y
  -- Summary: Same as upstream_g1_qualifiers_L3Y over a 5-year window
  IFNULL(m.upstream_g1_qualifiers_L5Y_count, 0) AS upstream_g1_qualifiers_L5Y,

  -- Field Name: coinvests_signal_inv_early_L3Y
  -- Summary: Early deals (last 3Y) where this investor co-invested alongside the signal list
  IFNULL(m.coinvests_signal_inv_early_L3Y_count, 0) AS coinvests_signal_inv_early_L3Y,

  -- Field Name: coinvests_g1_inv_early_L3Y
  -- Summary: Early deals (last 3Y) where this investor co-invested alongside the G1 signal list
  IFNULL(m.coinvests_g1_inv_early_L3Y_count, 0) AS coinvests_g1_inv_early_L3Y,

  -- Field Name: coinvests_signal_led_early_L3Y
  -- Summary: Early deals (last 3Y) where this investor co-invested in a signal-led round
  IFNULL(m.coinvests_signal_led_early_L3Y_count, 0) AS coinvests_signal_led_early_L3Y,

  -- Field Name: coinvests_g1_led_early_L3Y
  -- Summary: Early deals (last 3Y) where this investor co-invested in a G1-signal-led round
  IFNULL(m.coinvests_g1_led_early_L3Y_count, 0) AS coinvests_g1_led_early_L3Y,

  -- Field Name: percent_signal_inv_early_L3Y
  -- Summary: Share of this investor's early deals (last 3Y) where the signal list also invested
  SAFE_DIVIDE(IFNULL(m.coinvests_signal_inv_early_L3Y_count, 0), NULLIF(IFNULL(m.early_deals_L3Y_count, 0), 0)) AS percent_signal_inv_early_L3Y,

  -- Field Name: percent_g1_inv_early_L3Y
  -- Summary: Share of this investor's early deals (last 3Y) where the G1 signal list also invested
  SAFE_DIVIDE(IFNULL(m.coinvests_g1_inv_early_L3Y_count, 0), NULLIF(IFNULL(m.early_deals_L3Y_count, 0), 0)) AS percent_g1_inv_early_L3Y,

  -- Field Name: percent_signal_led_early_L3Y
  -- Summary: Share of this investor's early deals (last 3Y) where the signal list led the round
  SAFE_DIVIDE(IFNULL(m.coinvests_signal_led_early_L3Y_count, 0), NULLIF(IFNULL(m.early_deals_L3Y_count, 0), 0)) AS percent_signal_led_early_L3Y,

  -- Field Name: percent_g1_led_early_L3Y
  -- Summary: Share of this investor's early deals (last 3Y) where the G1 signal list led the round
  SAFE_DIVIDE(IFNULL(m.coinvests_g1_led_early_L3Y_count, 0), NULLIF(IFNULL(m.early_deals_L3Y_count, 0), 0)) AS percent_g1_led_early_L3Y,

  -- Field Name: qualifying_deal_names
  -- Summary: Comma-delimited list of qualifying company names, most recent first
  m.qualifying_deal_names_list AS qualifying_deal_names,

  -- Field Name: last_qualifying_deal_date
  -- Summary: Date of this investor's most recent qualifying deal
  m.last_qualifying_deal_date_value AS last_qualifying_deal_date

FROM `your-project-id.Clean.investors_clean` i
LEFT JOIN investor_deal_metrics m ON m.investor_name = i.investors;
