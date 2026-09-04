# Boot disk, kept as its own resource because the instance adopts an existing
# disk rather than creating one from initialize_params.
resource "google_compute_disk" "bot" {
  project = var.project_id
  name    = var.vm_name
  zone    = var.zone
  type    = "pd-standard"
  size    = var.vm_boot_disk_size_gb
  image   = var.vm_boot_image

  # The running disk drifts from its source image over time; don't let that
  # trigger a destroy/recreate.
  lifecycle {
    ignore_changes = [image, snapshot]
  }

  depends_on = [google_project_service.compute]
}

# The always-free e2-micro VM that runs the bot container. Deploys happen out of
# band (CI pulls the new image over IAP SSH and restarts the container), so the
# instance definition itself rarely changes.
resource "google_compute_instance" "bot" {
  project                    = var.project_id
  name                       = var.vm_name
  zone                       = var.zone
  machine_type               = var.vm_machine_type
  tags                       = ["http-server"]
  enable_display             = false
  key_revocation_action_type = "NONE"

  boot_disk {
    auto_delete = true
    device_name = var.vm_name
    source      = google_compute_disk.bot.self_link
  }

  network_interface {
    network    = "default"
    subnetwork = "default"

    access_config {
      network_tier = "PREMIUM"
    }
  }

  service_account {
    email  = google_service_account.vm.email
    scopes = ["cloud-platform"]
  }

  shielded_instance_config {
    enable_secure_boot          = false
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  metadata = {
    enable-oslogin = "TRUE"
  }

  # ssh-keys is churned by `gcloud compute ssh`'s ephemeral keys; attached_disk
  # covers any disks hot-attached outside Terraform.
  lifecycle {
    ignore_changes = [
      metadata["ssh-keys"],
      attached_disk,
    ]
  }
}

# Ingress SSH restricted to Google's IAP range, so CI can tunnel in without the
# VM exposing port 22 to the internet.
resource "google_compute_firewall" "allow_iap_ssh" {
  project       = var.project_id
  name          = "allow-iap-ssh"
  description   = "SSH only via IAP tunnel (OS Login)"
  network       = "default"
  direction     = "INGRESS"
  priority      = 1000
  source_ranges = ["35.235.240.0/20"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  depends_on = [google_project_service.compute]
}
