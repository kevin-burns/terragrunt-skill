# Template: AWS Provider Generation
# Generate AWS provider configuration with account validation

generate "provider" {
  path      = "{{path}}"
  if_exists = "{{if_exists}}"
  contents  = <<EOF
provider "aws" {
  region = "{{region}}"
  allowed_account_ids = ["{{account_id}}"]
}
EOF
}
