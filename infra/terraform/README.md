# Terraform — python-tg-bot infrastructure

Infrastructure-as-code for the GCP resources the bot's CI/CD relies on
(`.github/workflows/ci.yml`). All of it already exists in project
`project-048c89b2-4501-41c9-bc3` and was created by hand; this config **adopts**
it via `import` blocks so the first apply changes nothing (see caveat below).

## What is managed

| File | Resources |
|------|-----------|
| `apis.tf` | Enabled project services (Artifact Registry, Compute, IAM, IAP, OS Login, STS, Storage) |
| `artifact_registry.tf` | `python-tg-bot` Docker repo + reader/writer bindings |
| `iam.tf` | `github-deployer` and `python-tg-bot-vm` service accounts, project roles, VM-scoped roles |
| `workload_identity.tf` | `github-pool` pool, `github-provider` OIDC provider, branch-scoped impersonation binding |
| `compute.tf` | Bot VM, its boot disk, and the IAP-only SSH firewall rule |
| `state_bucket.tf` | GCS bucket for Terraform remote state |
| `imports.tf` | One-time `import` blocks; delete after the first successful apply |

Not managed: GCP-default firewall rules, default service accounts/agents, the
`.env` secrets on the VM (`/opt/python-tg-bot/.env`), and the DNS/Telegram side.

## Prerequisites

- Terraform >= 1.5
- `gcloud auth application-default login` as a user with `roles/owner` (or
  equivalent) on the project

## First-time bootstrap

The state bucket must exist before the `gcs` backend can be used:

```sh
cd infra/terraform

# 1. Init without a backend, create just the bucket (and its API).
terraform init -backend=false
terraform apply \
  -target=google_project_service.storage \
  -target=google_storage_bucket.tfstate

# 2. Switch to the remote backend and migrate the local state into it.
terraform init -migrate-state -backend-config=backend.hcl

# 3. Adopt everything else. Review the plan: it should be all imports,
#    with no create/update/replace except google_project_service.iam.
terraform plan
terraform apply
```

After a clean apply, delete `imports.tf` and commit.

## Day-to-day

```sh
terraform init -backend-config=backend.hcl   # first checkout on a new machine
terraform plan
terraform apply
```

Application deploys still happen through GitHub Actions, not Terraform — CI
builds the image, pushes it to Artifact Registry, and restarts the container on
the VM over IAP SSH.

## Caveats

- **`google_project_service.iam`** is not returned by `gcloud services list
  --enabled` today, so the first plan shows it as an addition. Enabling
  `iam.googleapis.com` is expected and required.
- The VM's `metadata["ssh-keys"]` and `attached_disk` are ignored
  (`lifecycle.ignore_changes`) because `gcloud compute ssh` rewrites ephemeral
  keys on every deploy.
- The boot disk ignores `image`/`snapshot` changes so a newer source image
  never forces disk recreation.
- If a `terraform plan` after import wants to *replace* the instance or disk,
  stop and reconcile the offending attribute in `compute.tf` instead of
  applying.

## Keeping CI in sync

`terraform output` prints the values used in `.github/workflows/ci.yml`:
`artifact_registry_image`, `deploy_service_account_email`,
`workload_identity_provider`, `vm_name`, `vm_zone`.
