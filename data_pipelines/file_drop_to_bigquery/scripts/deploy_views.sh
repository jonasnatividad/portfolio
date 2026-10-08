#!/usr/bin/env bash
# Create or replace every view, in dependency order: setup -> clean -> live -> prod.
# Usage: PROJECT=my-project ./scripts/deploy_views.sh
set -euo pipefail

PROJECT="${PROJECT:?set PROJECT to your GCP project id}"
cd "$(dirname "$0")/../sql"

run() {
  echo "-> $1"
  sed "s/your-gcp-project/${PROJECT}/g" "$1" | bq query --project_id="$PROJECT" --use_legacy_sql=false --quiet
}

run 00_setup.sql
for f in clean/companies.sql clean/deals.sql clean/deal_stage_history.sql \
         live/deal_pipeline.sql live/data_quality.sql \
         prod/pipeline_by_stage.sql prod/rep_scorecard.sql prod/forecast_by_month.sql; do
  run "$f"
done
echo "done"
