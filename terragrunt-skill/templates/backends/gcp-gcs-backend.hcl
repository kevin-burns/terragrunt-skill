# Template: GCP GCS Remote State Backend
# Configure Google Cloud Storage as remote state backend
# Variables:
#   {{bucket}} (required): GCS bucket name for remote state
#   {{prefix}} (required): Path prefix within bucket
#   {{project}} (optional, default=-): GCP project ID
#   {{credentials}} (optional, default=-): Path to GCP credentials file

remote_state {
  backend = "gcs"
  config = {
    bucket      = "{{bucket}}"
    prefix      = "{{prefix}}"
{{#project}}
    project     = "{{project}}"
{{/project}}
{{#credentials}}
    credentials = "{{credentials}}"
{{/credentials}}
  }
}
