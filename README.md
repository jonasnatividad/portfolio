# Jonas Natividad - Portfolio

Data engineer and analytics engineer. I build pipelines that move data into a warehouse,
model it so business users can trust it, and automate the reporting and tooling around
it. Everything in this repository is written from scratch on public or synthetic data.

## Data Engineering

| Project | What it shows | Tech |
|---|---|---|
| [Warehouse to Postgres Sync](data_pipelines/warehouse_to_postgres_sync) | Config-driven incremental replication from BigQuery to Postgres with watermarks, lookback, batch upserts and dry-run mode | Python, BigQuery, Postgres, Cloud Run, Cloud Scheduler, Secret Manager |
| [File Drop to BigQuery](data_pipelines/file_drop_to_bigquery) | Event-driven CSV ingestion, raw/clean/live/prod view layers, data quality gate, scheduled publish to Google Sheets | Python, Cloud Storage, Eventarc, Cloud Run, BigQuery SQL, gspread |

## Analytics Engineering

| Project | What it shows | Tech |
|---|---|---|
| [DST-Safe Daily Scheduling](analytics_engineering/time_handling/dst_safe_scheduling) | Running a job at a fixed local time across daylight saving changes: local-to-UTC conversion with explicit gap/overlap rules, an idempotent run guard, and tests for both transition days | BigQuery SQL, UDFs, scripting |

## Data Modeling

| Project | What it shows | Tech |
|---|---|---|
| [Omni Semantic Model: Online Retailer](data_modeling/omni_semantic_model_ecommerce) | Base views, relationships, SQL reporting views, a reconstructed daily status snapshot and curated topics on a public retail dataset | Omni (YAML), BigQuery, `thelook_ecommerce` |

## Automation

| Project | What it shows | Tech |
|---|---|---|
| [Reddit AI Assistant Bot](ai_automation/reddit_ai_assistant_bot) | Scheduled bot that finds question posts and replies with a link to a community assistant | Python, PRAW |
| [AI-Generated Hybrid Animals](ai_automation/ai_generated_hybrid_animals) | LLM-written prompts and captions, image generation, automatic posting to X | Python, OpenAI, Gemini, Tweepy |

## Web

| Project | What it shows | Tech |
|---|---|---|
| [All Jammed Up Festival Site](web_development/all_jammed_up_festival_site) | Single-page event site with map, podcast embed and social links | HTML, CSS, GitHub Pages |

## Conventions

- Project IDs, buckets and sheet IDs are placeholders (`your-gcp-project`, `your-drop-bucket`).
- Credentials are read from environment variables or Secret Manager; none are committed.
