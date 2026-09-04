# Remote state bucket. This is the one resource that must exist before the gcs
# backend can be used, so it is created during bootstrap with `-target` and
# local state, then state is migrated into it. See versions.tf.
resource "google_storage_bucket" "tfstate" {
  project  = var.project_id
  name     = var.state_bucket_name
  location = var.region

  uniform_bucket_level_access = true
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.storage]
}
