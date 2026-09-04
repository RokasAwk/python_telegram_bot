# Docker repository that holds the bot image built by CI
# (us-central1-docker.pkg.dev/<project>/python-tg-bot/python-tg-bot).
resource "google_artifact_registry_repository" "bot" {
  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_repo_id
  format        = "DOCKER"
  mode          = "STANDARD_REPOSITORY"

  depends_on = [google_project_service.artifactregistry]
}

# CI pushes images.
resource "google_artifact_registry_repository_iam_member" "deployer_writer" {
  project    = var.project_id
  location   = google_artifact_registry_repository.bot.location
  repository = google_artifact_registry_repository.bot.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.github_deployer.email}"
}

# The VM pulls images.
resource "google_artifact_registry_repository_iam_member" "vm_reader" {
  project    = var.project_id
  location   = google_artifact_registry_repository.bot.location
  repository = google_artifact_registry_repository.bot.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.vm.email}"
}
