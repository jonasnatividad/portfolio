-- One-time setup: datasets and raw tables.
-- Raw tables store every column as STRING exactly as it arrived, plus load
-- metadata. Typing and cleanup happen in the views, so a bad value never
-- blocks a load and the original file can always be reconstructed.

CREATE SCHEMA IF NOT EXISTS `your-gcp-project.sales_raw`   OPTIONS (location = 'US');
CREATE SCHEMA IF NOT EXISTS `your-gcp-project.sales_clean` OPTIONS (location = 'US');
CREATE SCHEMA IF NOT EXISTS `your-gcp-project.sales_live`  OPTIONS (location = 'US');
CREATE SCHEMA IF NOT EXISTS `your-gcp-project.sales_prod`  OPTIONS (location = 'US');

CREATE TABLE IF NOT EXISTS `your-gcp-project.sales_raw.companies` (
  company_id     STRING,
  company_name   STRING,
  industry       STRING,
  employee_band  STRING,
  country        STRING,
  account_owner  STRING,
  created_date   STRING,
  _source_file   STRING    NOT NULL,
  _file_date     DATE,
  _loaded_at     TIMESTAMP NOT NULL
)
PARTITION BY DATE(_loaded_at);

CREATE TABLE IF NOT EXISTS `your-gcp-project.sales_raw.deals` (
  deal_id              STRING,
  company_id           STRING,
  deal_name            STRING,
  plan                 STRING,
  stage                STRING,
  amount_usd           STRING,
  owner                STRING,
  created_date         STRING,
  expected_close_date  STRING,
  last_updated_at      STRING,
  _source_file         STRING    NOT NULL,
  _file_date           DATE,
  _loaded_at           TIMESTAMP NOT NULL
)
PARTITION BY DATE(_loaded_at);

-- Which files have been loaded. The loader checks this before loading, which
-- makes duplicate Cloud Storage notifications harmless.
CREATE TABLE IF NOT EXISTS `your-gcp-project.sales_raw._load_log` (
  source_file  STRING    NOT NULL,
  generation   STRING    NOT NULL,
  target_table STRING    NOT NULL,
  row_count    INT64,
  status       STRING    NOT NULL,   -- loaded | rejected
  message      STRING,
  loaded_at    TIMESTAMP NOT NULL
);
