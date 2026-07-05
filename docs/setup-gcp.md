# GCP deployment

Deploys the cloud tier: Pub/Sub topic (+ dead-letter), the Kotlin ingest service on
Cloud Run, and Cloud SQL (PostgreSQL). Everything is Terraform
([`cloud/terraform/`](../cloud/terraform/)) — nothing is created in the console.

**Cost expectations** (see [ADR-006](decisions/006-cloud-sql.md)): Cloud SQL
`db-f1-micro` ≈ **$10/month while it exists**; Cloud Run and Pub/Sub are ~$0 at this
volume (scale-to-zero / free tier). The teardown section below is not optional
reading.

## Prerequisites

- A GCP project with billing enabled; `gcloud` CLI authenticated (`gcloud auth login`,
  `gcloud auth application-default login`)
- Terraform ≥ 1.7

## 1. Build & push the ingest service image

Cloud Build compiles the Kotlin service remotely — no local Java needed:

```bash
cd cloud/ingest-service
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/costume-ingest:v1
```

## 2. Terraform the infrastructure

```bash
cd cloud/terraform
cp terraform.tfvars.example terraform.tfvars   # set project_id, region, image tag
terraform init
terraform plan     # review: ~12 resources
terraform apply
```

What gets created (see `main.tf` for the annotated source):

| Resource | Purpose |
|----------|---------|
| `google_pubsub_topic.sightings` (+ DLQ topic) | Event ingress from the Pi |
| `google_pubsub_subscription.push` | Pushes to Cloud Run; 5 attempts then dead-letter |
| `google_sql_database_instance` + db + user | PostgreSQL, smallest tier |
| `google_secret_manager_secret.db_password` | Generated password, injected into Cloud Run |
| `google_cloud_run_v2_service.ingest` | The Kotlin service, scale-to-zero |
| Service accounts + IAM bindings | Least privilege: edge SA can only publish; run SA can only reach the DB + secret |

Outputs include `edge_publisher_key_hint` — follow it to create/download the edge
service-account key.

## 3. Point the Pi at the cloud

On the Pi, add to `edge/.env`:

```ini
CLOUD_SYNC_ENABLED=true
GCP_PROJECT_ID=your-project-id
GCP_PUBSUB_TOPIC=costume-sightings
GOOGLE_APPLICATION_CREDENTIALS=/home/pi/costume-spotter-data/edge-publisher-key.json
```

Restart: `sudo systemctl restart costume-spotter`.

## 4. Verify end-to-end

```bash
# 1. Fake a sighting straight into the topic (no Pi needed):
gcloud pubsub topics publish costume-sightings --message \
  '{"id":"11111111-1111-1111-1111-111111111111","spotted_at":"2026-07-03T12:00:00Z","costume":"test pumpkin","confidence":"high","comment":"terraform says hi","device_id":"manual-test"}'

# 2. Watch the service wake up:
gcloud run services logs read costume-ingest --region YOUR_REGION --limit 20

# 3. Read it back through the service's API:
curl "$(terraform output -raw service_url)/api/sightings"
```

Then trigger a real sighting on the Pi and confirm it appears the same way. Publish
twice with the same `id` to see idempotency (07-F4): one row, no error.

## 5. Teardown (do this when not demoing)

```bash
terraform destroy          # removes everything, including the ~$10/mo database
```

To pause instead of destroy: `gcloud sql instances patch costume-db --activation-policy=NEVER`
(storage still bills, compute doesn't).

## CI/CD

[`.github/workflows/ci-cloud.yml`](../.github/workflows/ci-cloud.yml) builds and
tests the Kotlin service on every PR. Continuous *deployment* is intentionally not
wired up — for a personal-project GCP account, `gcloud builds submit` + `terraform
apply` from a trusted laptop is a smaller attack surface than granting GitHub Actions
deploy keys; the workflow file contains a commented sketch of the Workload Identity
Federation setup you'd use to enable it.
