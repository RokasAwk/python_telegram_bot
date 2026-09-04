# Adopt the resources that were created by hand into Terraform state.
#
# Run `terraform plan` — it should report imports with NO resource changes
# (aside from google_project_service.iam, see apis.tf). After the first
# successful `terraform apply`, this whole file can be deleted.

locals {
  ar_repo       = "projects/${var.project_id}/locations/${var.region}/repositories/${var.artifact_repo_id}"
  sa_vm         = "projects/${var.project_id}/serviceAccounts/python-tg-bot-vm@${var.project_id}.iam.gserviceaccount.com"
  sa_dep        = "projects/${var.project_id}/serviceAccounts/github-deployer@${var.project_id}.iam.gserviceaccount.com"
  mbr_vm        = "serviceAccount:python-tg-bot-vm@${var.project_id}.iam.gserviceaccount.com"
  mbr_dep       = "serviceAccount:github-deployer@${var.project_id}.iam.gserviceaccount.com"
  wif_pool_path = "projects/${var.project_id}/locations/global/workloadIdentityPools/github-pool"
}

# --- APIs (only the ones already enabled) --------------------------------

import {
  to = google_project_service.artifactregistry
  id = "${var.project_id}/artifactregistry.googleapis.com"
}

import {
  to = google_project_service.compute
  id = "${var.project_id}/compute.googleapis.com"
}

import {
  to = google_project_service.iamcredentials
  id = "${var.project_id}/iamcredentials.googleapis.com"
}

import {
  to = google_project_service.iap
  id = "${var.project_id}/iap.googleapis.com"
}

import {
  to = google_project_service.oslogin
  id = "${var.project_id}/oslogin.googleapis.com"
}

import {
  to = google_project_service.storage
  id = "${var.project_id}/storage.googleapis.com"
}

import {
  to = google_project_service.sts
  id = "${var.project_id}/sts.googleapis.com"
}

# --- Artifact Registry --------------------------------------------------

import {
  to = google_artifact_registry_repository.bot
  id = local.ar_repo
}

import {
  to = google_artifact_registry_repository_iam_member.deployer_writer
  id = "${local.ar_repo} roles/artifactregistry.writer ${local.mbr_dep}"
}

import {
  to = google_artifact_registry_repository_iam_member.vm_reader
  id = "${local.ar_repo} roles/artifactregistry.reader ${local.mbr_vm}"
}

# --- Service accounts -------------------------------------------------

import {
  to = google_service_account.vm
  id = local.sa_vm
}

import {
  to = google_service_account.github_deployer
  id = local.sa_dep
}

# --- Project IAM --------------------------------------------------------

import {
  to = google_project_iam_member.deployer_compute_viewer
  id = "${var.project_id} roles/compute.viewer ${local.mbr_dep}"
}

import {
  to = google_project_iam_member.deployer_iap_tunnel
  id = "${var.project_id} roles/iap.tunnelResourceAccessor ${local.mbr_dep}"
}

# --- Deployer access scoped to the VM --------------------------------

import {
  to = google_compute_instance_iam_member.deployer_os_admin_login
  id = "projects/${var.project_id}/zones/${var.zone}/instances/${var.vm_name} roles/compute.osAdminLogin ${local.mbr_dep}"
}

import {
  to = google_service_account_iam_member.deployer_actas_vm_sa
  id = "${local.sa_vm} roles/iam.serviceAccountUser ${local.mbr_dep}"
}

# --- Workload Identity Federation -----------------------------------

import {
  to = google_iam_workload_identity_pool.github
  id = local.wif_pool_path
}

import {
  to = google_iam_workload_identity_pool_provider.github
  id = "${local.wif_pool_path}/providers/github-provider"
}

import {
  to = google_service_account_iam_member.deployer_workload_identity_user
  id = "${local.sa_dep} roles/iam.workloadIdentityUser principalSet://iam.googleapis.com/projects/${var.project_number}/locations/global/workloadIdentityPools/github-pool/attribute.ref/refs/heads/${var.deploy_branch}"
}

# --- Compute ----------------------------------------------------------

import {
  to = google_compute_disk.bot
  id = "projects/${var.project_id}/zones/${var.zone}/disks/${var.vm_name}"
}

import {
  to = google_compute_instance.bot
  id = "projects/${var.project_id}/zones/${var.zone}/instances/${var.vm_name}"
}

import {
  to = google_compute_firewall.allow_iap_ssh
  id = "projects/${var.project_id}/global/firewalls/allow-iap-ssh"
}
