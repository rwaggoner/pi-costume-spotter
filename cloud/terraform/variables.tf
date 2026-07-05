# Inputs — set real values in terraform.tfvars (never committed; see .gitignore).

variable "project_id" {
  description = "GCP project to deploy into (billing must be enabled)."
  type        = string
}

variable "region" {
  description = "Region for Cloud Run, Cloud SQL, and Pub/Sub resources."
  type        = string
  default     = "us-central1"
}

variable "ingest_image" {
  description = "Container image for the ingest service, e.g. gcr.io/PROJECT/costume-ingest:v1 (built via docs/setup-gcp.md §1)."
  type        = string
}

variable "db_tier" {
  description = "Cloud SQL machine tier. db-f1-micro is the cheapest (~$10/mo) and plenty (ADR-006)."
  type        = string
  default     = "db-f1-micro"
}
