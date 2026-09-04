output "artifact_registry_image" {
  description = "Base image path CI should build/push to."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.bot.repository_id}/${var.artifact_repo_id}"
}

output "deploy_service_account_email" {
  description = "Value for the DEPLOY_SERVICE_ACCOUNT env in .github/workflows/ci.yml."
  value       = google_service_account.github_deployer.email
}

output "workload_identity_provider" {
  description = "Value for the WORKLOAD_IDENTITY_PROVIDER env in .github/workflows/ci.yml."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "vm_name" {
  description = "Compute Engine instance name."
  value       = google_compute_instance.bot.name
}

output "vm_zone" {
  description = "Compute Engine instance zone."
  value       = google_compute_instance.bot.zone
}

output "vm_external_ip" {
  description = "Ephemeral external IP of the bot VM."
  value       = google_compute_instance.bot.network_interface[0].access_config[0].nat_ip
}

output "vm_service_account_email" {
  description = "Runtime identity attached to the VM."
  value       = google_service_account.vm.email
}
