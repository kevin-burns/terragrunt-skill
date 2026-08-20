# Template: GCP GCS Advanced Remote State Backend
# Advanced Google Cloud Storage backend with KMS encryption, service account impersonation, and custom endpoint support
# Variables:
#   {{bucket}} (required): GCS bucket name for remote state
#   {{prefix}} (required): Path prefix within bucket
#   {{project}} (optional, default=-): GCP project ID
#   {{credentials}} (optional, default=-): Path to GCP credentials file
#   {{location}} (optional, default=-): Storage location for data residency requirements
#   {{encryption_key}} (optional, default=-): Customer-supplied encryption key (Base64-encoded 256-bit)
#   {{kms_encryption_key}} (optional, default=-): Cloud KMS key name for encryption
#   {{impersonate_service_account}} (optional, default=-): Service account email for impersonation
#   {{storage_custom_endpoint}} (optional, default=-): Custom storage endpoint URL (for emulators or private endpoints)

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
{{#location}}
    location    = "{{location}}"
{{/location}}
{{#encryption_key}}
    encryption_key = "{{encryption_key}}"
{{/encryption_key}}
{{#kms_encryption_key}}
    kms_encryption_key = "{{kms_encryption_key}}"
{{/kms_encryption_key}}
{{#impersonate_service_account}}
    impersonate_service_account = "{{impersonate_service_account}}"
{{/impersonate_service_account}}
{{#storage_custom_endpoint}}
    storage_custom_endpoint = "{{storage_custom_endpoint}}"
{{/storage_custom_endpoint}}
  }
}
