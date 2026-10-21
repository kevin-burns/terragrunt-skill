# Template: Azure Blob Storage Advanced Remote State Backend
# Advanced Azure Blob Storage backend with multiple authentication methods (Service Principal, MSI, SAS Token, Azure AD) and snapshot support
# Variables:
#   {{resource_group_name}} (required): Resource group containing storage account
#   {{storage_account_name}} (required): Storage account name
#   {{container_name}} (required): Blob container name
#   {{key}} (required): Path to state file within container
#   {{subscription_id}} (optional, default=-): Azure subscription ID (optional for scoped access)
#   {{tenant_id}} (optional, default=-): Azure AD tenant ID for authentication
#   {{client_id}} (optional, default=-): Service principal client ID
#   {{client_secret}} (optional, default=-): Service principal client secret
#   {{use_msi}} (optional, default=-): Use Managed Service Identity for authentication
#   {{sas_token}} (optional, default=-): Storage SAS token for authentication
#   {{snapshot}} (optional, default=-): Enable snapshot support for point-in-time recovery
#   {{use_azuread_auth}} (optional, default=-): Use Azure AD authentication instead of access keys

# NOTE: below Terragrunt v1.2.0, remote_state backend "azurerm" passes through to the
# native OpenTofu/Terraform azurerm backend and Terragrunt creates nothing (v1.1.2-v1.1.6:
# unless --experiment azure-backend). On v1.2.0+ `--backend-bootstrap` provisions the
# resource group, storage account and container. Establish the version first; see
# references/azure-backend.md.
# Ref: https://docs.terragrunt.com/reference/experiments/completed/#azure-backend

remote_state {
  backend = "azurerm"
  config = {
    resource_group_name  = "{{resource_group_name}}"
    storage_account_name = "{{storage_account_name}}"
    container_name       = "{{container_name}}"
    key                  = "{{key}}"
{{#subscription_id}}
    subscription_id      = "{{subscription_id}}"
{{/subscription_id}}
{{#tenant_id}}
    tenant_id            = "{{tenant_id}}"
{{/tenant_id}}
{{#client_id}}
    client_id            = "{{client_id}}"
{{/client_id}}
{{#client_secret}}
    client_secret        = "{{client_secret}}"
{{/client_secret}}
{{#use_msi}}
    use_msi              = {{use_msi}}
{{/use_msi}}
{{#sas_token}}
    sas_token            = "{{sas_token}}"
{{/sas_token}}
{{#snapshot}}
    snapshot             = {{snapshot}}
{{/snapshot}}
{{#use_azuread_auth}}
    use_azuread_auth     = {{use_azuread_auth}}
{{/use_azuread_auth}}
  }
}
