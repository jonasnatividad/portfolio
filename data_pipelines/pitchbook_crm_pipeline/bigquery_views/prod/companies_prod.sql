-- View: Pitchbook.prod.companies_prod
-- Enriches companies_clean with deal-derived signal flags, round labels,
-- and investor matching against the signal and G1 signal investor lists.
-- Joins to deals_prod for per-company aggregations.

SELECT
  c.*,

  -- Field Name: last_rd_series_consolidated
  -- Summary: Simplified series label for the company's last financing round
  -- Logic: Checks last_financing_deal_type and last_financing_deal_type_2 in sequence
  CASE
    WHEN LOWER(TRIM(c.last_financing_deal_type)) = 'accelerator/incubator' THEN 'Seed'
    WHEN REGEXP_CONTAINS(COALESCE(c.last_financing_deal_type, ''), r'(?i)angel') THEN 'Seed'
    WHEN LOWER(TRIM(c.last_financing_deal_type_2)) = 'seed round' THEN 'Seed'
    WHEN REGEXP_CONTAINS(COALESCE(c.last_financing_deal_type_2, ''), r'(?i)angel') THEN 'Seed'
    WHEN REGEXP_CONTAINS(COALESCE(c.last_financing_deal_type_2, ''), r'(?i)series\s*A') THEN 'Series A'
    WHEN REGEXP_CONTAINS(COALESCE(c.last_financing_deal_type_2, ''), r'(?i)series\s*B') THEN 'Series B'
    WHEN REGEXP_CONTAINS(COALESCE(c.last_financing_deal_type_2, ''), r'(?i)series\s*C') THEN 'Series C'
    WHEN REGEXP_CONTAINS(COALESCE(c.last_financing_deal_type_2, ''), r'(?i)series\s*D') THEN 'Series D'
    WHEN REGEXP_CONTAINS(COALESCE(c.last_financing_deal_type_2, ''), r'(?i)series\s*E') THEN 'Series E'
    WHEN REGEXP_CONTAINS(COALESCE(c.last_financing_deal_type_2, ''), r'(?i)series\s*F') THEN 'Series F'
    WHEN REGEXP_CONTAINS(COALESCE(c.last_financing_deal_type_2, ''), r'(?i)series\s*G') THEN 'Series G'
    WHEN REGEXP_CONTAINS(COALESCE(c.last_financing_deal_type_2, ''), r'(?i)series\s*H') THEN 'Series H'
    WHEN REGEXP_CONTAINS(COALESCE(c.last_financing_deal_type_2, ''), r'(?i)series\s*I') THEN 'Series I'
    WHEN REGEXP_CONTAINS(COALESCE(c.last_financing_deal_type_2, ''), r'(?i)series\s*J') THEN 'Series J'
    WHEN REGEXP_CONTAINS(COALESCE(c.last_financing_deal_type_2, ''), r'(?i)series\s*K') THEN 'Series K'
  END AS last_rd_series_consolidated,

  COALESCE(g1.has_g1_led_a, FALSE) AS g1_led_a,
  ld.lead_sole_investors_firm_only AS last_round_lead,
  COALESCE(sbe.has_signal_backed_early, FALSE) AS signal_backed_early,
  COALESCE(sle.has_signal_led_early, FALSE) AS signal_led_early,
  COALESCE(g1sbe.has_g1_signal_backed_early, FALSE) AS g1_signal_backed_early,
  COALESCE(g1sle.has_g1_signal_led_early, FALSE) AS g1_signal_led_early,
  COALESCE(src.signal_led_count, 0) AS signal_led_round_count,
  COALESCE(src.g1_led_count, 0) AS g1_led_round_count,
  src.max_deal_no AS rds_raised,
  SAFE_DIVIDE(src.signal_led_count, src.max_deal_no) AS signal_led_percent,
  SAFE_DIVIDE(src.g1_led_count, src.max_deal_no) AS g1_signal_led_percent,
  COALESCE(ld.signal_led, FALSE) AS last_round_signal_led,
  ld.meg_filter_stage AS meg_filter_stage,
  COALESCE(g1_last.is_g1_led, FALSE) AS last_round_g1_led,

  -- Signal investors (full names from active_investors matched to signal_investors_prod)
  si.signal_investors,

  -- Signal investors shorthand
  si_short.signal_investors_short,

  -- Signal lead investors (full names from deals lead_sole_investors matched to signal_investors_prod)
  sli.signal_lead_investors,

  -- Signal lead investors shorthand
  sli_short.signal_lead_investors_short

FROM `your-project-id`.`Clean`.`companies_clean` AS c

-- G1-led Series A
LEFT JOIN (
  SELECT DISTINCT company_id, TRUE AS has_g1_led_a
  FROM `your-project-id`.`Prod`.`deals_prod`
  WHERE g1_signal_led IS TRUE AND deal_series_consolidated = 'Series A'
) AS g1 ON c.company_id = g1.company_id

-- Most recent deal info
LEFT JOIN (
  SELECT company_id, lead_sole_investors_firm_only, signal_led, meg_filter_stage, deal_rank
  FROM (
    SELECT company_id, lead_sole_investors_firm_only, signal_led, meg_filter_stage,
      ROW_NUMBER() OVER (PARTITION BY company_id ORDER BY deal_date DESC NULLS LAST) AS deal_rank
    FROM `your-project-id`.`Prod`.`deals_prod`
  )
  WHERE deal_rank = 1
) AS ld ON c.company_id = ld.company_id

-- Signal backed early
LEFT JOIN (
  SELECT DISTINCT company_id, TRUE AS has_signal_backed_early
  FROM `your-project-id`.`Prod`.`deals_prod`
  WHERE signal_invested IS TRUE AND REGEXP_CONTAINS(COALESCE(stage_indicators, ''), r'(?i)early')
) AS sbe ON c.company_id = sbe.company_id

-- Signal led early
LEFT JOIN (
  SELECT DISTINCT company_id, TRUE AS has_signal_led_early
  FROM `your-project-id`.`Prod`.`deals_prod`
  WHERE signal_led IS TRUE AND REGEXP_CONTAINS(COALESCE(stage_indicators, ''), r'(?i)early')
) AS sle ON c.company_id = sle.company_id

-- G1 signal backed early
LEFT JOIN (
  SELECT DISTINCT company_id, TRUE AS has_g1_signal_backed_early
  FROM `your-project-id`.`Prod`.`deals_prod`
  WHERE g1_signal_invested IS TRUE AND REGEXP_CONTAINS(COALESCE(stage_indicators, ''), r'(?i)early')
) AS g1sbe ON c.company_id = g1sbe.company_id

-- G1 signal led early
LEFT JOIN (
  SELECT DISTINCT company_id, TRUE AS has_g1_signal_led_early
  FROM `your-project-id`.`Prod`.`deals_prod`
  WHERE g1_signal_led IS TRUE AND REGEXP_CONTAINS(COALESCE(stage_indicators, ''), r'(?i)early')
) AS g1sle ON c.company_id = g1sle.company_id

-- Signal round counts
LEFT JOIN (
  SELECT company_id,
    COUNT(CASE WHEN signal_led IS TRUE THEN 1 END) AS signal_led_count,
    COUNT(CASE WHEN g1_signal_led IS TRUE THEN 1 END) AS g1_led_count,
    MAX(deal_no) AS max_deal_no
  FROM `your-project-id`.`Prod`.`deals_prod`
  GROUP BY company_id
) AS src ON c.company_id = src.company_id

-- G1 last round led check
LEFT JOIN (
  SELECT DISTINCT ld_outer.company_id, TRUE AS is_g1_led
  FROM (
    SELECT company_id, lead_sole_investors_firm_only,
      ROW_NUMBER() OVER (PARTITION BY company_id ORDER BY deal_date DESC NULLS LAST) AS deal_rank
    FROM `your-project-id`.`Prod`.`deals_prod`
  ) AS ld_outer
  CROSS JOIN `your-project-id`.`Prod`.`g1_signal_investors_prod` AS g1i
  WHERE ld_outer.deal_rank = 1
    AND ld_outer.lead_sole_investors_firm_only IS NOT NULL
    AND (
      ld_outer.lead_sole_investors_firm_only = g1i.investors
      OR REGEXP_CONTAINS(CONCAT(', ', ld_outer.lead_sole_investors_firm_only, ', '),
                         CONCAT(', ', g1i.investors, ', '))
    )
) AS g1_last ON c.company_id = g1_last.company_id

-- Signal investors (full names)
LEFT JOIN (
  SELECT
    c2.company_id,
    STRING_AGG(DISTINCT TRIM(inv), ', ' ORDER BY TRIM(inv)) AS signal_investors
  FROM `your-project-id`.`Clean`.`companies_clean` AS c2,
  UNNEST(SPLIT(c2.active_investors, ',')) AS inv
  INNER JOIN `your-project-id`.`Prod`.`signal_investors_prod` AS sip
    ON TRIM(inv) = sip.investors
  WHERE c2.active_investors IS NOT NULL
  GROUP BY c2.company_id
) AS si ON c.company_id = si.company_id

-- Signal investors (shorthand)
LEFT JOIN (
  SELECT
    c2.company_id,
    STRING_AGG(DISTINCT sip.short_name, ', ' ORDER BY sip.short_name) AS signal_investors_short
  FROM `your-project-id`.`Clean`.`companies_clean` AS c2,
  UNNEST(SPLIT(c2.active_investors, ',')) AS inv
  INNER JOIN `your-project-id`.`Prod`.`signal_investors_prod` AS sip
    ON TRIM(inv) = sip.investors
  WHERE c2.active_investors IS NOT NULL
    AND sip.short_name IS NOT NULL
  GROUP BY c2.company_id
) AS si_short ON c.company_id = si_short.company_id

-- Signal lead investors (full names)
LEFT JOIN (
  SELECT
    d.company_id,
    STRING_AGG(DISTINCT TRIM(lead_inv), ', ' ORDER BY TRIM(lead_inv)) AS signal_lead_investors
  FROM `your-project-id`.`Prod`.`deals_prod` AS d,
  UNNEST(SPLIT(d.lead_sole_investors, ',')) AS lead_inv
  INNER JOIN `your-project-id`.`Prod`.`signal_investors_prod` AS sip
    ON TRIM(lead_inv) = sip.investors
  WHERE d.lead_sole_investors IS NOT NULL
  GROUP BY d.company_id
) AS sli ON c.company_id = sli.company_id

-- Signal lead investors (shorthand)
LEFT JOIN (
  SELECT
    d.company_id,
    STRING_AGG(DISTINCT sip.short_name, ', ' ORDER BY sip.short_name) AS signal_lead_investors_short
  FROM `your-project-id`.`Prod`.`deals_prod` AS d,
  UNNEST(SPLIT(d.lead_sole_investors, ',')) AS lead_inv
  INNER JOIN `your-project-id`.`Prod`.`signal_investors_prod` AS sip
    ON TRIM(lead_inv) = sip.investors
  WHERE d.lead_sole_investors IS NOT NULL
    AND sip.short_name IS NOT NULL
  GROUP BY d.company_id
) AS sli_short ON c.company_id = sli_short.company_id;
