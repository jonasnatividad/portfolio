# Scheduling and Triggers

| Step | Trigger | When |
|---|---|---|
| CRM export lands in `gs://your-drop-bucket/incoming/<table>/` | Upstream export job or a person | Daily, around 05:00 New York time |
| `csv-loader` | Eventarc, on object finalize | Within seconds of each file landing |
| Clean / live / prod views | None needed (they are views) | Always current at query time |
| `sales-sheet-refresh` | Cloud Scheduler | 07:00 America/New_York, Monday-Friday |

The loader is event-driven, so there is no polling and no fixed load time. The views do
no work until queried. Only the publish step runs on a clock, and it refuses to publish
if the data quality view reports stale or broken data, so a late export shows up as a
"blocked" response in logs instead of a sheet full of yesterday's numbers.

## Eventarc trigger for the loader

```bash
PROJECT=your-gcp-project
REGION=us-central1
BUCKET=your-drop-bucket

# Cloud Storage must be allowed to publish events
GCS_SA=$(gcloud storage service-agent --project $PROJECT)
gcloud projects add-iam-policy-binding $PROJECT \
  --member serviceAccount:$GCS_SA --role roles/pubsub.publisher

gcloud eventarc triggers create csv-loader-on-upload \
  --project $PROJECT --location $REGION \
  --destination-run-service csv-loader --destination-run-region $REGION \
  --event-filters type=google.cloud.storage.object.v1.finalized \
  --event-filters bucket=$BUCKET \
  --service-account csv-loader@$PROJECT.iam.gserviceaccount.com
```

The trigger fires for every object in the bucket; the loader ignores anything outside
`incoming/`, which includes its own moves to `processed/` and `rejected/`.

## Cloud Scheduler job for the sheet refresh

```bash
URL=$(gcloud run services describe sales-sheet-refresh --region $REGION --project $PROJECT --format 'value(status.url)')

gcloud scheduler jobs create http sales-sheet-refresh \
  --project $PROJECT --location $REGION \
  --schedule "0 7 * * 1-5" --time-zone "America/New_York" \
  --uri "$URL/refresh" --http-method POST \
  --oidc-service-account-email scheduler-invoker@$PROJECT.iam.gserviceaccount.com \
  --attempt-deadline 600s --max-retry-attempts 3 --min-backoff 15m
```

`--time-zone America/New_York` keeps the job at 07:00 local through daylight saving
changes. The retry policy (three attempts, 15 minutes apart) gives a late export until
about 08:00 to arrive before the run gives up.

## Optional: refresh right after a load

If the team wants the sheet updated as soon as a new file is processed, have the loader
publish a Pub/Sub message after a successful `deals` load and add a push subscription to
`/refresh`. Keep the scheduled job as a backstop.
