# Template: GCP (google) Provider Generation
# Generate a google provider configuration.
# Variables:
#   {{path}} (required): generated file path, e.g. provider.tf
#   {{if_exists}} (required): overwrite | overwrite_terragrunt | skip | error
#   {{project}} (required HERE, though optional to the provider — see the warning below)
#   {{region}} (required): default region for regional resources
#   {{zone}} (optional, default=-): default zone for zonal resources
#   {{impersonate_service_account}} (optional, default=-): service account to impersonate
#
# THE REASON THIS TEMPLATE SETS project EXPLICITLY.
#   Every argument on the google provider is OPTIONAL — verified against the provider
#   reference on 2026-08-19. There is no `allowed_account_ids` and no equivalent of any
#   kind: nothing in the argument list constrains WHICH project you deploy to. Compare
#   AWS, which has `allowed_account_ids`, and azurerm v4, which makes `subscription_id`
#   mandatory. GCP has neither.
#
#   An unset `project` therefore falls back to GOOGLE_PROJECT, then to Application Default
#   Credentials, then to gcloud's active configuration — on a laptop, whatever the engineer
#   last ran `gcloud config set project` against. The plan succeeds against the wrong
#   project and nothing warns.
#
#   Set it explicitly, and DERIVE it from the directory tree rather than typing it, so the
#   path and the target cannot disagree:
#     locals { project_id = local.env_vars.locals.project_id }
#
# AUTHENTICATION.
#   Prefer Workload Identity Federation in CI over a `credentials` key file — see
#   references/cicd.md. `impersonate_service_account` requires
#   roles/iam.serviceAccountTokenCreator on the target account; without it the call fails at
#   plan with a permission error naming the impersonation rather than the resource.
#
# QUOTA / BILLING.
#   `user_project_override` defaults to false, and `billing_project` is IGNORED unless it is
#   true. Setting billing_project alone does nothing and reports no error.

generate "provider" {
  path      = "{{path}}"
  if_exists = "{{if_exists}}"
  contents  = <<EOF
provider "google" {
  project = "{{project}}"
  region  = "{{region}}"
{{#zone}}
  zone    = "{{zone}}"
{{/zone}}
{{#impersonate_service_account}}
  impersonate_service_account = "{{impersonate_service_account}}"
{{/impersonate_service_account}}
}
EOF
}
