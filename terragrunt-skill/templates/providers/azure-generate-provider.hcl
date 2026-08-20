# Template: Azure (azurerm) Provider Generation
# Generate an azurerm provider configuration.
# Variables:
#   {{path}} (required): generated file path, e.g. provider.tf
#   {{if_exists}} (required): overwrite | overwrite_terragrunt | skip | error
#   {{subscription_id}} (required): Azure subscription ID — REQUIRED by azurerm provider v4+
#                       (or set ARM_SUBSCRIPTION_ID). Only omittable when use_cli=true on
#                       provider >= v4.35.0. See references/azure-backend.md.
#
# Notes:
#   - features {} is mandatory for the azurerm provider.
#   - use_azuread_auth lets data-plane calls use Entra ID; for CI prefer OIDC
#     (use_oidc = true) over client_secret. Pin the provider in required_providers so the
#     v4 subscription_id rule is predictable.

generate "provider" {
  path      = "{{path}}"
  if_exists = "{{if_exists}}"
  contents  = <<EOF
provider "azurerm" {
  features {}
  subscription_id  = "{{subscription_id}}"
  use_azuread_auth = true
}
EOF
}
