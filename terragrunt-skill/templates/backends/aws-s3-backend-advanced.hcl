# Template: AWS S3 Advanced Remote State Backend
# Advanced S3 backend with KMS encryption, cross-account access, and custom endpoint support
# Variables:
#   {{bucket}} (required): S3 bucket name for Terraform state
#   {{key}} (required): Path to state file within bucket
#   {{region}} (required): AWS region for S3 bucket
#   {{dynamodb_table}} (optional, default=-): DynamoDB table for state locking
#   {{encrypt}} (optional, default=-): Enable encryption at rest
#   {{kms_key_id}} (optional, default=-): KMS key ARN for server-side encryption
#   {{role_arn}} (optional, default=-): IAM role ARN for cross-account access
#   {{session_name}} (optional, default=-): Session name for assumed role
#   {{profile}} (optional, default=-): AWS CLI profile name for authentication
#   {{endpoint}} (optional, default=-): Custom S3 endpoint URL (for LocalStack/MinIO)
#   {{workspace_key_prefix}} (optional, default=-): Prefix for workspace-specific state files
#   {{skip_credentials_validation}} (optional, default=-): Skip AWS credentials validation

remote_state {
  backend = "s3"
  config = {
    bucket         = "{{bucket}}"
    key            = "{{key}}"
    region         = "{{region}}"
{{#dynamodb_table}}
    dynamodb_table = "{{dynamodb_table}}"
{{/dynamodb_table}}
{{#encrypt}}
    encrypt        = {{encrypt}}
{{/encrypt}}
{{#kms_key_id}}
    kms_key_id     = "{{kms_key_id}}"
{{/kms_key_id}}
{{#role_arn}}
    role_arn       = "{{role_arn}}"
{{/role_arn}}
{{#session_name}}
    session_name   = "{{session_name}}"
{{/session_name}}
{{#profile}}
    profile        = "{{profile}}"
{{/profile}}
{{#endpoint}}
    endpoint       = "{{endpoint}}"
{{/endpoint}}
{{#workspace_key_prefix}}
    workspace_key_prefix = "{{workspace_key_prefix}}"
{{/workspace_key_prefix}}
{{#skip_credentials_validation}}
    skip_credentials_validation = {{skip_credentials_validation}}
{{/skip_credentials_validation}}
  }
}
