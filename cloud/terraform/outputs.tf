# What you need after `terraform apply` (used in docs/setup-gcp.md §3–4).

output "service_url" {
  description = "The ingest service's URL (read API + health)."
  value       = google_cloud_run_v2_service.ingest.uri
}

output "topic" {
  description = "Topic the Pi publishes to (GCP_PUBSUB_TOPIC in edge/.env)."
  value       = google_pubsub_topic.sightings.name
}

output "db_connection_name" {
  description = "Cloud SQL connection name, for `gcloud sql connect` debugging."
  value       = google_sql_database_instance.db.connection_name
}

output "edge_publisher_key_hint" {
  description = "How to mint the Pi's credentials (kept manual on purpose — key files should be a deliberate act)."
  value       = "gcloud iam service-accounts keys create edge-publisher-key.json --iam-account=${google_service_account.edge_publisher.email}"
}
