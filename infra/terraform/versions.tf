terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # Remote state lives in the GCS bucket created by state_bucket.tf.
  #
  # Bootstrap (first run only), from this directory:
  #   terraform init -backend=false
  #   terraform apply -target=google_project_service.storage \
  #                   -target=google_storage_bucket.tfstate
  #   terraform init -migrate-state -backend-config=backend.hcl
  #
  # After that, plain `terraform init` / `plan` / `apply` use the bucket.
  backend "gcs" {}
}
