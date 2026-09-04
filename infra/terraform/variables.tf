variable "project_id" {
  description = "GCP project ID that hosts the bot."
  type        = string
  default     = "project-048c89b2-4501-41c9-bc3"
}

variable "project_number" {
  description = "GCP project number (used in Workload Identity principal sets)."
  type        = string
  default     = "547977652248"
}

variable "region" {
  description = "Default region for regional resources (Artifact Registry, subnet)."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "Zone for the Compute Engine VM and its disk."
  type        = string
  default     = "us-central1-a"
}

variable "github_repository" {
  description = "owner/repo allowed to mint tokens through Workload Identity Federation."
  type        = string
  default     = "RokasAwk/python_telegram_bot"
}

variable "deploy_branch" {
  description = "Git branch on github_repository permitted to impersonate the deployer SA."
  type        = string
  default     = "main"
}

variable "artifact_repo_id" {
  description = "Artifact Registry repository ID for the bot image."
  type        = string
  default     = "python-tg-bot"
}

variable "vm_name" {
  description = "Name of the Compute Engine instance (and its boot disk) running the bot."
  type        = string
  default     = "instance-20260821-030618"
}

variable "vm_machine_type" {
  description = "Machine type for the bot VM."
  type        = string
  default     = "e2-micro"
}

variable "vm_boot_image" {
  description = "Source image for the boot disk."
  type        = string
  default     = "projects/ubuntu-os-cloud/global/images/ubuntu-minimal-2604-resolute-amd64-v20260723"
}

variable "vm_boot_disk_size_gb" {
  description = "Boot disk size in GB."
  type        = number
  default     = 30
}

variable "state_bucket_name" {
  description = "GCS bucket that holds Terraform remote state. Must match backend.hcl."
  type        = string
  default     = "project-048c89b2-4501-41c9-bc3-tfstate"
}
