# Template: Azure Blob Storage Remote State Backend
# Configure Azure Blob Storage backend with Azure AD authentication
# Variables:
#   {{subscription_id}} (required): Azure subscription ID
#   {{resource_group_name}} (required): Resource group containing storage account
#   {{storage_account_name}} (required): Storage account name
#   {{container_name}} (required): Blob container name
#   {{key}} (required): Path to state file within container

# NOTE: by default remote_state backend "azurerm" passes through to the native
# OpenTofu/Terraform azurerm backend — Terragrunt does NOT bootstrap/migrate/delete
# Azure storage, so unlike S3/GCS the storage account + container must already exist
# before init. This template assumes that default. As of Terragrunt v1.1.2 the
# azure-backend experiment is no longer a no-op: on v1.1.2+ with
# `--experiment azure-backend`, Terragrunt does bootstrap and manage them. See
# references/azure-backend.md before assuming either. use_azuread_auth=true is
# Microsoft-recommended (avoids storage shared keys, often disabled by policy); the
# deploying identity then needs the "Storage Blob Data Contributor" data-plane role.
# Full detail + gotchas: references/azure-backend.md
# Ref: https://docs.terragrunt.com/reference/experiments/active

remote_state {
  backend = "azurerm"
  config = {
    subscription_id      = "{{subscription_id}}"
    resource_group_name  = "{{resource_group_name}}"
    storage_account_name = "{{storage_account_name}}"
    container_name       = "{{container_name}}"
    key                  = "{{key}}"
    use_azuread_auth     = true
  }
}
