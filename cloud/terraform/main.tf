# ---------------------------------------------------------------------------
# Costume Spotter cloud tier — all of it (07-F8: nothing is click-created).
#
# Shape (see docs/architecture.md#cloud-tier):
#   Pi --publish--> Pub/Sub topic --push--> Cloud Run (Kotlin) --JDBC--> Cloud SQL
#                        \--after 5 failed deliveries--> dead-letter topic
#
# Cost model: Cloud Run and Pub/Sub scale to zero; the Cloud SQL instance is
# the only idle cost (~$10/mo on db-f1-micro). Teardown: `terraform destroy`
# (docs/setup-gcp.md §5).
# ---------------------------------------------------------------------------

terraform {
  required_version = ">= 1.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# --- APIs the stack needs (idempotent to re-apply) --------------------------

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "pubsub.googleapis.com",
    "secretmanager.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

# --- Event ingress: topic, dead-letter topic, push subscription -------------

resource "google_pubsub_topic" "sightings" {
  name       = "costume-sightings"
  depends_on = [google_project_service.apis]
}

resource "google_pubsub_topic" "dead_letter" {
  # Poison messages land here after max delivery attempts (07-F5); nothing
  # consumes it automatically — it exists to be inspected by a human.
  name       = "costume-sightings-dead-letter"
  depends_on = [google_project_service.apis]
}

resource "google_pubsub_subscription" "push_to_ingest" {
  name  = "costume-sightings-push"
  topic = google_pubsub_topic.sightings.id

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.ingest.uri}/pubsub"
    oidc_token {
      # Pub/Sub authenticates to Cloud Run as this SA — the service stays
      # closed to the public internet while still receiving pushes.
      service_account_email = google_service_account.pubsub_pusher.email
    }
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter.id
    max_delivery_attempts = 5
  }

  retry_policy {
    minimum_backoff = "10s" # transient ingest failures back off rather than hammer
  }
}

# Pub/Sub's service agent must be allowed to dead-letter and to re-publish.
data "google_project" "this" {}

resource "google_pubsub_topic_iam_member" "dlq_publisher" {
  topic  = google_pubsub_topic.dead_letter.id
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_subscription_iam_member" "dlq_subscriber" {
  subscription = google_pubsub_subscription.push_to_ingest.id
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

# --- Database: Cloud SQL (PostgreSQL) — ADR-006 -----------------------------

resource "google_sql_database_instance" "db" {
  name             = "costume-db"
  database_version = "POSTGRES_16"
  region           = var.region

  settings {
    tier = var.db_tier # db-f1-micro: the whole point is minimal idle cost
    ip_configuration {
      ipv4_enabled = true # connections come via the Cloud SQL connector, not raw IP
    }
  }
  # A portfolio project's database should be destroyable without ceremony.
  deletion_protection = false
  depends_on          = [google_project_service.apis]
}

resource "google_sql_database" "costume" {
  name     = "costume"
  instance = google_sql_database_instance.db.name
}

resource "random_password" "db_password" {
  length  = 24
  special = false
}

resource "google_sql_user" "ingest" {
  name     = "ingest"
  instance = google_sql_database_instance.db.name
  password = random_password.db_password.result
}

# The password's home is Secret Manager (07-N4); Cloud Run reads it from there.
resource "google_secret_manager_secret" "db_password" {
  secret_id = "costume-db-password"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db_password.result
}

# --- Service accounts: least privilege (07-N3) ------------------------------

# The Pi. Can publish to the one topic; can do nothing else in the project.
resource "google_service_account" "edge_publisher" {
  account_id   = "costume-edge-publisher"
  display_name = "Costume Spotter edge device (publish-only)"
}

resource "google_pubsub_topic_iam_member" "edge_can_publish" {
  topic  = google_pubsub_topic.sightings.id
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.edge_publisher.email}"
}

# Pub/Sub's push identity. May invoke the Cloud Run service; nothing else.
resource "google_service_account" "pubsub_pusher" {
  account_id   = "costume-pubsub-pusher"
  display_name = "Pub/Sub push -> ingest service"
}

resource "google_cloud_run_v2_service_iam_member" "pusher_can_invoke" {
  name     = google_cloud_run_v2_service.ingest.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.pubsub_pusher.email}"
}

# The ingest service. May connect to Cloud SQL and read its one secret.
resource "google_service_account" "ingest_runtime" {
  account_id   = "costume-ingest-runtime"
  display_name = "Ingest service runtime"
}

resource "google_project_iam_member" "ingest_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.ingest_runtime.email}"
}

resource "google_secret_manager_secret_iam_member" "ingest_reads_password" {
  secret_id = google_secret_manager_secret.db_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.ingest_runtime.email}"
}

# --- The service: Cloud Run v2, scale-to-zero (07-N1) ------------------------

resource "google_cloud_run_v2_service" "ingest" {
  name     = "costume-ingest"
  location = var.region
  # Only authenticated identities (the pusher SA) may call it.
  ingress = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.ingest_runtime.email

    scaling {
      min_instance_count = 0 # scale-to-zero: idle costs nothing
      max_instance_count = 2 # porch-scale traffic does not need more
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.db.connection_name]
      }
    }

    containers {
      image = var.ingest_image

      env {
        name = "DB_URL"
        # Socket-factory URL: the Cloud SQL Java connector handles auth + TLS
        # (see cloud/ingest-service/.../Database.kt for the matching client side).
        value = "jdbc:postgresql:///${google_sql_database.costume.name}?cloudSqlInstance=${google_sql_database_instance.db.connection_name}&socketFactory=com.google.cloud.sql.postgres.SocketFactory"
      }
      env {
        name  = "DB_USER"
        value = google_sql_user.ingest.name
      }
      env {
        name = "DB_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_password.secret_id
            version = "latest"
          }
        }
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      resources {
        limits = {
          memory = "512Mi" # a lean Ktor app; JVM flags default fine at this size
          cpu    = "1"
        }
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_version.db_password,
    google_secret_manager_secret_iam_member.ingest_reads_password,
  ]
}
