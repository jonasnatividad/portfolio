-- View: Pitchbook.prod.deals_prod
-- Enriches deals_clean with computed fields across three dependency layers:
--   Layer 1 (deals_base):       base calculations with no inter-dependencies
--   Layer 2 (deals_with_stages): fields that depend on Layer 1
--   Layer 3 (final SELECT):     fields that reference Layer 2 (upstream checks)
--
-- Key computed fields:
--   deal_series_consolidated  — normalized round label (Seed / Series A–K)
--   stage_indicators          — 'Early', 'Breakout', or both
--   meg_filter_stage          — valuation-based stage bucket for deal flow filtering
--   signal_led / signal_invested           — matched against signal_investors_prod
--   g1_signal_led / g1_signal_invested     — matched against g1_signal_investors_prod
--   filter_qualification      — 'Qualifies' / 'May Qualify' / 'Not Qualify'
--   upstream_signal_led / upstream_qualifier / upstream_g1_qualifier
--                             — TRUE if a later deal for the same company meets the condition

WITH

-- Layer 1: Base calculations with no inter-dependencies
deals_base AS (
  SELECT
    d.*,

    -- Field Name: then_current_raised
    -- Summary: Raised-to-date minus this deal's size, nulls treated as 0
    IFNULL(d.raised_to_date, 0) - IFNULL(d.deal_size, 0) AS then_current_raised,

    -- Field Name: lead_sole_investors_firm_only
    -- Summary: Lead/sole investors cleaned of trailing parenthetical notes
    REGEXP_REPLACE(IFNULL(d.lead_sole_investors, ''), r'\s*\([^()]*\)', '') AS lead_sole_investors_firm_only,

    -- Field Name: investors_firm_only
    -- Summary: All investors cleaned of trailing parenthetical notes
    REGEXP_REPLACE(IFNULL(d.investors, ''), r'\s*\([^()]*\)', '') AS investors_firm_only,

    -- Field Name: deal_series_consolidated
    -- Summary: Simplified round label mapped to Seed or Series A–K
    CASE
      WHEN d.deal_type = 'Accelerator/Incubator' THEN 'Seed'
      WHEN d.deal_type = 'Seed Round' THEN 'Seed'
      WHEN LOWER(d.deal_type) LIKE '%angel%' THEN 'Seed'
      WHEN d.deal_type_2 = 'Seed Round' OR LOWER(d.deal_type_2) LIKE '%angel%' THEN 'Seed'
      -- Series AA: only consolidate to A if deal_type is Early Stage VC or Seed Round
      WHEN LOWER(d.deal_type_2) LIKE '%series aa%' AND d.deal_type IN ('Early Stage VC', 'Seed Round') THEN 'Series A'
      WHEN LOWER(d.deal_type_2) LIKE '%series aa%' THEN 'Series AA'
      -- Series BB: only consolidate to B if deal_type is Early Stage VC
      WHEN LOWER(d.deal_type_2) LIKE '%series bb%' AND d.deal_type = 'Early Stage VC' THEN 'Series B'
      WHEN LOWER(d.deal_type_2) LIKE '%series bb%' THEN 'Series BB'
      WHEN LOWER(d.deal_type_2) LIKE '%series a%' THEN 'Series A'
      WHEN LOWER(d.deal_type_2) LIKE '%series b%' THEN 'Series B'
      WHEN LOWER(d.deal_type_2) LIKE '%series c%' THEN 'Series C'
      WHEN LOWER(d.deal_type_2) LIKE '%series d%' THEN 'Series D'
      WHEN LOWER(d.deal_type_2) LIKE '%series e%' THEN 'Series E'
      WHEN LOWER(d.deal_type_2) LIKE '%series f%' THEN 'Series F'
      WHEN LOWER(d.deal_type_2) LIKE '%series g%' THEN 'Series G'
      WHEN LOWER(d.deal_type_2) LIKE '%series h%' THEN 'Series H'
      WHEN LOWER(d.deal_type_2) LIKE '%series i%' THEN 'Series I'
      WHEN LOWER(d.deal_type_2) LIKE '%series j%' THEN 'Series J'
      WHEN LOWER(d.deal_type_2) LIKE '%series k%' THEN 'Series K'
      ELSE NULL
    END AS deal_series_consolidated,

    -- Field Name: investable_deal_type
    -- Summary: TRUE if deal_type is in the approved investable list or deal_class is Venture Capital
    CASE
      WHEN d.deal_type IN (
        'Accelerator/Incubator', 'Seed Round', 'Early Stage VC', 'Late Stage VC',
        'Angel (individual)', 'Secondary Transaction - Private',
        'Secondary Transaction - Open Market', 'Convertible Debt', 'PE/Growth Expansion'
      ) THEN TRUE
      WHEN d.deal_class = 'Venture Capital' THEN TRUE
      ELSE FALSE
    END AS investable_deal_type

  FROM `your-project-id.Clean.deals_clean` AS d
),

-- Layer 2: Fields that depend on Layer 1 calculations
deals_with_stages AS (
  SELECT
    db.*,

    -- Field Name: stage_indicators
    -- Summary: Outputs 'Early', 'Breakout', or 'Early, Breakout'
    -- Logic: Two independent tests joined as array; null entries are dropped by ARRAY_TO_STRING
    ARRAY_TO_STRING([
      CASE
        WHEN db.post_valuation < 150
          OR db.then_current_raised < 15
          OR (db.deal_type = 'Early Stage VC' AND db.deal_size < 20)
          OR db.deal_no = 1
          OR db.deal_type IN ('Accelerator/Incubator', 'Seed Round')
          OR LOWER(db.deal_type) LIKE '%angel%'
          OR db.deal_type_2 = 'Seed Round'
          OR LOWER(db.deal_type_2) LIKE '%angel%'
        THEN 'Early'
      END,
      CASE
        WHEN (db.post_valuation BETWEEN 150 AND 750)
          OR (db.deal_type = 'Early Stage VC' AND db.deal_size BETWEEN 15 AND 75)
        THEN 'Breakout'
      END
    ], ', ') AS stage_indicators,

    -- Field Name: meg_filter_stage
    -- Summary: Valuation-based stage bucket for deal flow filtering
    -- Logic: Prioritizes investability check, then post_valuation thresholds with deal_size fallbacks
    CASE
      WHEN db.investable_deal_type = FALSE THEN 'Not Investable'
      WHEN db.deal_type = 'Accelerator/Incubator' THEN 'Pre-Filter'
      WHEN db.post_valuation < 100 THEN 'Pre-Filter'
      WHEN db.post_valuation IS NULL AND db.deal_size < 20 THEN 'Pre-Filter'
      WHEN db.post_valuation IS NULL AND db.deal_size IS NULL AND db.then_current_raised < 10 THEN 'Pre-Filter'
      WHEN db.post_valuation IS NULL AND db.deal_size IS NULL AND db.deal_type = 'Seed Round' THEN 'Pre-Filter'
      WHEN db.post_valuation IS NULL AND db.deal_type = 'Angel (individual)' THEN 'Pre-Filter'
      WHEN db.post_valuation BETWEEN 100 AND 150 THEN '100-150m'
      WHEN db.post_valuation IS NULL AND db.deal_size >= 20 AND db.deal_size < 30 THEN '100-150m'
      WHEN db.post_valuation BETWEEN 150 AND 3000 THEN '150M-3B'
      WHEN db.post_valuation IS NULL AND db.deal_size >= 30 AND db.deal_size < 150 THEN '150M-3B'
      WHEN db.post_valuation BETWEEN 3000 AND 5000 THEN '3-5B'
      WHEN db.post_valuation IS NULL AND db.deal_size >= 150 AND db.deal_size < 250 THEN '3-5B'
      WHEN db.post_valuation >= 5000 THEN '5B+'
      WHEN db.post_valuation IS NULL AND db.deal_size >= 250 THEN '3-5B'
      ELSE NULL
    END AS meg_filter_stage,

    -- Field Name: signal_led
    -- Summary: TRUE if any lead/sole investor is in the signal investor list
    EXISTS (
      SELECT 1
      FROM UNNEST(
        ARRAY(SELECT TRIM(x) FROM UNNEST(SPLIT(db.lead_sole_investors_firm_only, ',')) AS x WHERE TRIM(x) <> '')
      ) AS inv
      JOIN `your-project-id.Prod.signal_investors_prod` s ON LOWER(inv) = LOWER(s.Investors)
    ) AS signal_led,

    -- Field Name: g1_signal_led
    -- Summary: TRUE if any lead/sole investor is in the G1 signal investor list
    EXISTS (
      SELECT 1
      FROM UNNEST(
        ARRAY(SELECT TRIM(x) FROM UNNEST(SPLIT(db.lead_sole_investors_firm_only, ',')) AS x WHERE TRIM(x) <> '')
      ) AS inv
      JOIN `your-project-id.Prod.g1_signal_investors_prod` s ON LOWER(inv) = LOWER(s.Investors)
    ) AS g1_signal_led,

    -- Field Name: signal_invested
    -- Summary: TRUE if any investor (not only lead) is in the signal investor list
    EXISTS (
      SELECT 1
      FROM UNNEST(
        ARRAY(SELECT TRIM(x) FROM UNNEST(SPLIT(db.investors_firm_only, ',')) AS x WHERE TRIM(x) <> '')
      ) AS inv
      JOIN `your-project-id.Prod.signal_investors_prod` s ON LOWER(inv) = LOWER(s.Investors)
    ) AS signal_invested,

    -- Field Name: g1_signal_invested
    -- Summary: TRUE if any investor (not only lead) is in the G1 signal investor list
    EXISTS (
      SELECT 1
      FROM UNNEST(
        ARRAY(SELECT TRIM(x) FROM UNNEST(SPLIT(db.investors_firm_only, ',')) AS x WHERE TRIM(x) <> '')
      ) AS inv
      JOIN `your-project-id.Prod.g1_signal_investors_prod` s ON LOWER(inv) = LOWER(s.Investors)
    ) AS g1_signal_invested

  FROM deals_base AS db
)

-- Layer 3: Final SELECT with fields that reference Layer 2
SELECT
  dws.*,

  -- Field Name: filter_qualification
  -- Summary: Qualifies / May Qualify / Not Qualify based on signal-led and stage bucket
  CASE
    WHEN dws.signal_led = TRUE AND dws.meg_filter_stage = '150M-3B' THEN 'Qualifies'
    WHEN dws.signal_led = TRUE AND dws.meg_filter_stage IN ('100-150m', '3-5B', '5B+') THEN 'May Qualify'
    ELSE 'Not Qualify'
  END AS filter_qualification,

  -- Field Name: upstream_signal_led
  -- Summary: TRUE if any later deal for this company is signal-led
  EXISTS (
    SELECT 1
    FROM deals_with_stages later
    WHERE later.company_id = dws.company_id
      AND later.deal_no > dws.deal_no
      AND later.signal_led = TRUE
      AND later.investable_deal_type = TRUE
  ) AS upstream_signal_led,

  -- Field Name: upstream_qualifier
  -- Summary: TRUE if any later deal is signal-led and lands in a qualifying stage bucket
  EXISTS (
    SELECT 1
    FROM deals_with_stages later
    WHERE later.company_id = dws.company_id
      AND later.deal_no > dws.deal_no
      AND later.signal_led = TRUE
      AND later.investable_deal_type = TRUE
      AND later.meg_filter_stage IS NOT NULL
      AND later.meg_filter_stage NOT IN ('Pre-Filter', '5B+', 'Not Investable')
  ) AS upstream_qualifier,

  -- Field Name: upstream_g1_qualifier
  -- Summary: TRUE if any later deal is G1-signal-led and lands in a qualifying stage bucket
  EXISTS (
    SELECT 1
    FROM deals_with_stages later
    WHERE later.company_id = dws.company_id
      AND later.deal_no > dws.deal_no
      AND later.g1_signal_led = TRUE
      AND later.investable_deal_type = TRUE
      AND later.meg_filter_stage IS NOT NULL
      AND later.meg_filter_stage NOT IN ('Pre-Filter', '5B+', 'Not Investable')
  ) AS upstream_g1_qualifier

FROM deals_with_stages AS dws;
