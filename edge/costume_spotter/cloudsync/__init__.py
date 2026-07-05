"""Optional cloud sync: publish sightings to GCP Pub/Sub (docs/requirements/07-cloud.md).

Loaded only when CLOUD_SYNC_ENABLED=true — the edge is fully functional without
any cloud at all (architecture principle #3).
"""
