# --- Service accounts -------------------------------------------------------

# Runtime identity attached to the bot VM.
resource "google_service_account" "vm" {
  project      = var.project_id
  account_id   = "python-tg-bot-vm"
  display_name = "python-tg-bot VM runtime identity"
  description  = "Attached to instance-20260821-030618; only needs to pull the bot image from Artifact Registry"

  depends_on = [google_project_service.iam]
}

# Identity assumed by GitHub Actions (via Workload Identity Federation) to
# push images and restart the container over IAP SSH.
resource "google_service_account" "github_deployer" {
  project      = var.project_id
  account_id   = "github-deployer"
  display_name = "GitHub Actions CD deployer"
  description  = "Used by GitHub Actions to push images to Artifact Registry and deploy to the bot VM"

  depends_on = [google_project_service.iam]
}

# --- Project-level roles for the deployer ---------------------------------

resource "google_project_iam_member" "deployer_compute_viewer" {
  project = var.project_id
  role    = "roles/compute.viewer"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

resource "google_project_iam_member" "deployer_iap_tunnel" {
  project = var.project_id
  role    = "roles/iap.tunnelResourceAccessor"
  member  = "serviceAccount:${google_service_account.github_deployer.email}"
}

# --- Deployer access scoped to the VM -----------------------------------

# SSH into the instance through OS Login (as an admin, matching current state).
resource "google_compute_instance_iam_member" "deployer_os_admin_login" {
  project       = var.project_id
  zone          = var.zone
  instance_name = google_compute_instance.bot.name
  role          = "roles/compute.osAdminLogin"
  member        = "serviceAccount:${google_service_account.github_deployer.email}"
}

# Needed so the deployer can log in to a VM that runs as the vm service account.
resource "google_service_account_iam_member" "deployer_actas_vm_sa" {
  service_account_id = google_service_account.vm.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.github_deployer.email}"
}
