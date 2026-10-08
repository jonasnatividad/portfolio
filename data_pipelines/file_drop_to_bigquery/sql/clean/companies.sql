-- CLEAN layer: one row per company, typed and tidied.
-- Rules: trim text, cast types safely (bad values become NULL, not errors),
-- keep the most recent version of each company across all loaded files.
CREATE OR REPLACE VIEW `your-gcp-project.sales_clean.companies` AS
WITH typed AS (
  SELECT
    NULLIF(TRIM(company_id), '')                          AS company_id,
    NULLIF(REGEXP_REPLACE(TRIM(company_name), r'\s+', ' '), '') AS company_name,
    NULLIF(TRIM(industry), '')                            AS industry,
    NULLIF(TRIM(employee_band), '')                       AS employee_band,
    UPPER(NULLIF(TRIM(country), ''))                      AS country_code,
    INITCAP(NULLIF(TRIM(account_owner), ''))              AS account_owner,
    SAFE.PARSE_DATE('%Y-%m-%d', TRIM(created_date))       AS created_date,
    _source_file,
    _file_date,
    _loaded_at
  FROM `your-gcp-project.sales_raw.companies`
)
SELECT * EXCEPT (version_rank)
FROM (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY company_id
      ORDER BY _file_date DESC, _loaded_at DESC
    ) AS version_rank
  FROM typed
  WHERE company_id IS NOT NULL
)
WHERE version_rank = 1;
