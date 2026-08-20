# Template: AWS S3 Remote State Backend
# Configure S3 backend with DynamoDB locking for AWS
# Variables:
#   {{bucket}} (required): S3 bucket name for Terraform state
#   {{key}} (required): Path to state file within bucket
#   {{region}} (required): AWS region for S3 bucket
#   {{dynamodb_table}} (required): DynamoDB table for state locking
#   {{encrypt}} (optional, default=-): Enable encryption at rest

remote_state {
  backend = "s3"
  config = {
    bucket         = "{{bucket}}"
    key            = "{{key}}"
    region         = "{{region}}"
    encrypt        = {{encrypt}}
    dynamodb_table = "{{dynamodb_table}}"
  }
}
