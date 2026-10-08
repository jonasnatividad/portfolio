-- CLEAN layer: one row per deal (current version), typed and standardized.
-- Each daily export is a full snapshot, so the same deal appears in many
-- files. Keep the version with the latest last_updated_at; break ties with
-- the newest file. Exact duplicate rows inside a file collapse the same way.
CREATE OR REPLACE VIEW `your-gcp-project.sales_clean.deals` AS
WITH typed AS (
  SELECT
    NULLIF(TRIM(deal_id), '')                                     AS deal_id,
    NULLIF(TRIM(company_id), '')                                  AS company_id,
    NULLIF(TRIM(deal_name), '')                                   AS deal_name,
    INITCAP(NULLIF(TRIM(plan), ''))                               AS plan,
    -- ' closed won ' / 'CLOSED WON' / 'Closed Won' -> 'Closed Won'
    INITCAP(REGEXP_REPLACE(TRIM(stage), r'\s+', ' '))             AS stage,
    -- '$17,800.00' / '17800' -> 17800; blank -> NULL
    SAFE_CAST(REGEXP_REPLACE(amount_usd, r'[$,\s]', '') AS NUMERIC) AS amount_usd,
    INITCAP(NULLIF(TRIM(owner), ''))                              AS owner,
    SAFE.PARSE_DATE('%Y-%m-%d', TRIM(created_date))               AS created_date,
    SAFE.PARSE_DATE('%Y-%m-%d', TRIM(expected_close_date))        AS expected_close_date,
    SAFE.PARSE_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', TRIM(last_updated_at)) AS last_updated_at,
    _source_file,
    _file_date,
    _loaded_at
  FROM `your-gcp-project.sales_raw.deals`
)
SELECT
  * EXCEPT (version_rank),
  stage IN ('Closed Won', 'Closed Lost') AS is_closed,
  stage = 'Closed Won'                   AS is_won,
  amount_usd IS NULL                     AS is_missing_amount
FROM (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY deal_id
      ORDER BY last_updated_at DESC, _file_date DESC, _loaded_at DESC
    ) AS version_rank
  FROM typed
  WHERE deal_id IS NOT NULL
)
WHERE version_rank = 1;
