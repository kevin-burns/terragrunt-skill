# Terragrunt Error Diagnosis Playbook

> Source: curated data harvested from omattsson/terragrunt-mcp-server, restructured for grep-based lookup.
> Content spot-checked against docs.terragrunt.com at **v1.1.0** (2026-07-01) and updated for **v1.1.1** (2026-07-14). Flag and avoid any pre-1.0 idioms.

Workflow: take the error text, grep this file for distinctive keywords (`grep -in 'state lock' error-patterns.md`), then read the matching ERROR section.

**If the user has a `terragrunt-crash-*.log` file, start there, not here.** Since v1.1.1 Terragrunt
writes `terragrunt-crash-YYYYMMDDTHHMMSSZ-<pid>.log` when it *panics* — a crash in Terragrunt
itself, carrying the command line, panic message and stack trace. That is a different animal from
the configuration and provider errors catalogued below: nothing in this file will fix it, and it is
worth reporting upstream with the log attached. Check the pinned version against the latest release
first — several v1.1.1 fixes were for crashes (`run --all` dependency discovery with graph filters,
`--filter-allow-destroy` over deleted units with dependents), so an older pin may simply be the
cause.

## Categories
- **authentication** (3): AWS credentials not found, Azure authentication required, GCP credentials not found
- **backend** (5): S3 bucket does not exist, Access denied to backend, GCS bucket not found, Azure storage account not found, Azure backend 403 (shared key disabled / missing RBAC)
- **provider** (1): azurerm provider requires subscription_id (v4+)
- **configuration** (38): No Terraform configuration files found, Syntax error in configuration, Missing required input variable, Invalid configuration block, Duplicate configuration block, Invalid attribute value, Required attribute missing, Invalid terraform source…
- **dependency** (13): Circular dependency detected, Module not found, Could not download source, Git authentication failed, Git ref not found, Module subdirectory not found, Module registry unavailable, Module checksum mismatch…
- **network** (2): Network timeout, Connection refused
- **state** (3): Error acquiring state lock, Backend configuration changed, Failed to get existing workspaces
- **terraform** (3): Terraform version constraint not met, Provider not found, Provider version constraint

## ERROR: AWS credentials not found

**Category:** authentication

AWS credentials are not configured or invalid

**Likely causes:**
- AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY not set
- No AWS profile configured
- Credentials are expired or invalid

**Solutions:**

```bash
aws configure
```

## ERROR: Azure authentication required

**Category:** authentication

Not authenticated to Azure or subscription not accessible

**Likely causes:**
- Not logged in to Azure CLI
- Azure subscription not selected
- Service principal credentials invalid

**Solutions:**

```bash
az login
```
```bash
az account set --subscription <subscription-id>
```

## ERROR: GCP credentials not found

**Category:** authentication

GCP credentials are not configured

**Likely causes:**
- GOOGLE_APPLICATION_CREDENTIALS not set
- Not authenticated with gcloud
- Service account key file missing

**Solutions:**

```bash
gcloud auth application-default login
```

## ERROR: Access denied to backend

**Category:** backend

Insufficient permissions to access the backend storage

**Likely causes:**
- AWS/Azure/GCP credentials are invalid
- IAM policy does not grant required permissions
- Bucket policy restricts access
- (Azure) data-plane RBAC role missing for Entra ID auth — see the dedicated 403 entry below

**Solutions:**
- Re-authenticate / verify the active principal (`aws sts get-caller-identity`,
  `az account show`, `gcloud auth list`).
- Grant the minimum backend permissions (S3+lock table / GCS bucket / Storage Blob Data
  Contributor on the account).
- For Azure specifics, see "Azure backend 403" below and references/azure-backend.md.

## ERROR: Azure storage account not found

**Category:** backend

The Azure storage account for remote state does not exist

**Likely causes:**
- Storage account name is incorrect
- Storage account does not exist
- Wrong Azure subscription
- **Expecting Terragrunt to create it** — it won't. Unlike S3/GCS, Terragrunt does NOT
  bootstrap Azure storage (the `azure-backend` experiment is a no-op); the account and
  container must be created out-of-band.

**Solutions:**

- Verify the account exists in the right subscription:
```bash
az storage account show --name <account-name> --subscription <subscription-id>
```
- Create the account + container out-of-band (see references/azure-backend.md):
```bash
az storage account create -n <account-name> -g <rg> -l <region> --kind StorageV2
az storage container create -n <container> --account-name <account-name> --auth-mode login
```

## ERROR: Azure backend 403 (AuthorizationFailure / shared key access disabled)

**Category:** backend

`init` against the azurerm backend fails with 403 (Forbidden) / AuthorizationFailure

**Likely causes:**
- The storage account has `allowSharedKeyAccess = false` (common enterprise policy), so the
  backend's default shared-key auth is rejected.
- Using Entra ID auth but the identity lacks a **data-plane** RBAC role. ARM
  Owner/Contributor do NOT grant blob data access.

**Solutions:**
- Switch to Entra ID auth in the backend config: `use_azuread_auth = true` (or `use_oidc` in
  CI).
- Assign a data-plane role to the deploying identity:
```bash
az role assignment create --assignee <objectId> \
  --role "Storage Blob Data Contributor" \
  --scope <storage-account-resource-id>
```
- Allow up to ~10 min (30 at MG scope) for the role assignment to propagate.

## ERROR: azurerm provider requires subscription_id (v4+)

**Category:** provider

`azurerm` provider v4+ errors that the subscription ID is required

**Likely causes:**
- Provider upgraded to v4.0.0+ (2024-08-22), which **requires** `subscription_id`.

**Solutions:**
- Set it in the provider block (`subscription_id = "..."`) or export `ARM_SUBSCRIPTION_ID`.
- Only omittable when `use_cli = true` on provider ≥ v4.35.0. See references/azure-backend.md.
- Pin the provider in `required_providers` so the behavior is predictable.

## ERROR: GCS bucket not found

**Category:** backend

The GCS bucket for remote state does not exist

**Likely causes:**
- Bucket name is incorrect
- Bucket does not exist in the project
- Wrong GCP project selected

**Solutions:**

```bash
gsutil ls gs://<bucket-name>
```

## ERROR: S3 bucket does not exist

**Category:** backend

The S3 bucket specified for remote state does not exist

**Likely causes:**
- Bucket name is incorrect
- Bucket does not exist in the specified region
- Bucket was deleted

**Solutions:**

```bash
aws s3 ls s3://<bucket-name>
```

## ERROR: After apply hook failed

**Category:** configuration

After apply hook execution failed

**Likely causes:**
- Post-deployment script error
- Resources not yet available
- Notification service unreachable

## ERROR: Before init hook failed

**Category:** configuration

Before init hook execution failed

**Likely causes:**
- Initialization dependencies not met
- Script path incorrect
- Environment not ready

## ERROR: Circular dependency in locals

**Category:** configuration

Local variables have circular dependencies

**Likely causes:**
- Local A references local B which references local A
- Indirect circular reference through multiple locals
- Self-referencing local

## ERROR: Circular include detected

**Category:** configuration

Include files create a circular reference

**Likely causes:**
- File A includes file B which includes file A
- Indirect circular include through multiple files
- Self-referencing include

## ERROR: Configuration path not found

**Category:** configuration

Referenced file or directory does not exist

**Likely causes:**
- Path is incorrect
- File was moved or deleted
- Relative path resolved incorrectly

## ERROR: Duplicate configuration block

**Category:** configuration

Configuration block defined multiple times

**Likely causes:**
- Same block appears twice in terragrunt.hcl
- Block inherited from include and redefined
- Merged includes have duplicate blocks

## ERROR: Function evaluation error

**Category:** configuration

Error evaluating Terragrunt function

**Likely causes:**
- Function arguments are invalid
- Function not available in this context
- Runtime error in function execution

## ERROR: Generate if_exists strategy error

**Category:** configuration

Invalid if_exists strategy in generate block

**Likely causes:**
- Invalid strategy value
- Strategy not applicable to situation
- Typo in strategy name

## ERROR: Generate invalid path

**Category:** configuration

Generated file path is invalid

**Likely causes:**
- Path contains invalid characters
- Path traversal outside working directory
- Absolute path not allowed

## ERROR: Generate permission denied

**Category:** configuration

Insufficient permissions to write generated file

**Likely causes:**
- Directory is read-only
- File ownership issue
- SELinux or security policy blocking

## ERROR: Generate template error

**Category:** configuration

Error in generate block template

**Likely causes:**
- Invalid HCL in contents
- Template interpolation failed
- Function error in contents

## ERROR: Generated file already exists

**Category:** configuration

Generated file already exists and cannot be overwritten

**Likely causes:**
- File manually created with same name
- Previous generation not cleaned up
- Multiple generates target same file

## ERROR: Hook command failed

**Category:** configuration

Before or after hook command failed

**Likely causes:**
- Command not found
- Script error
- Insufficient permissions

## ERROR: Hook environment variable missing

**Category:** configuration

Required environment variable for hook is missing

**Likely causes:**
- Environment variable not exported
- Variable name typo
- Shell context different

## ERROR: Hook execution timeout

**Category:** configuration

Hook command exceeded timeout

**Likely causes:**
- Command takes too long
- Process hung or stuck
- Timeout value too low

## ERROR: Hook log suppression error

**Category:** configuration

Error with hook log suppression configuration

**Likely causes:**
- Invalid suppress_stdout value
- Logging configuration conflict
- Output redirection failed

## ERROR: Hook working directory error

**Category:** configuration

Cannot access hook working directory

**Likely causes:**
- Directory does not exist
- Permissions issue
- Path resolution failed

## ERROR: Include dependency resolution error

**Category:** configuration

Cannot resolve dependencies in included configuration

**Likely causes:**
- Dependency defined in include not accessible
- Output reference invalid
- Dependency execution order wrong

## ERROR: Include expose configuration conflict

**Category:** configuration

Conflict in include expose configuration

**Likely causes:**
- Multiple includes expose same block
- Expose configuration incompatible
- Invalid expose value

## ERROR: Include file not found

**Category:** configuration

Referenced include file does not exist

**Likely causes:**
- Include path is incorrect
- File was moved or deleted
- Path resolution failed

## ERROR: Include file parse error

**Category:** configuration

Syntax error in included file

**Likely causes:**
- HCL syntax error in include file
- Invalid configuration structure
- Encoding issues

## ERROR: Include merge conflict

**Category:** configuration

Cannot merge configurations from includes

**Likely causes:**
- Conflicting block definitions
- Incompatible merge strategies
- Duplicate keys with different values

## ERROR: Include path traversal limit

**Category:** configuration

Exceeded limit searching for include file

**Likely causes:**
- File not found in any parent directory
- Traversal reached filesystem root
- Fallback path not configured

## ERROR: Interpolation error

**Category:** configuration

Error in variable interpolation or template

**Likely causes:**
- Variable not defined
- Invalid interpolation syntax
- Circular reference in interpolation

## ERROR: Invalid attribute value

**Category:** configuration

Invalid or unsupported attribute in configuration

**Likely causes:**
- Attribute value is wrong type
- Attribute not supported for this block
- Typo in attribute name

## ERROR: Invalid configuration block

**Category:** configuration

Invalid or unsupported block in terragrunt.hcl

**Likely causes:**
- Typo in block name
- Block not supported in this version
- Block in wrong location

## ERROR: Invalid terraform source

**Category:** configuration

The terraform source URL format is invalid

**Likely causes:**
- Malformed URL or path
- Unsupported source type
- Missing required URL components

## ERROR: Local evaluation error

**Category:** configuration

Error evaluating local variable expression

**Likely causes:**
- Function call failed
- Type error in expression
- Null or undefined value

## ERROR: Local type error

**Category:** configuration

Local variable has wrong type

**Likely causes:**
- Expression evaluates to unexpected type
- Type conversion failed
- Collection type mismatch

## ERROR: Locals merge error

**Category:** configuration

Error merging locals from includes

**Likely causes:**
- Conflicting local definitions
- Type incompatibility
- Merge strategy not specified

## ERROR: Missing required input variable

**Category:** configuration

A required input variable is not provided

**Likely causes:**
- Input not defined in inputs block
- Variable not passed from parent terragrunt.hcl
- Typo in variable name

## ERROR: No Terraform configuration files found

**Category:** configuration

Terragrunt cannot find any .tf files in the source directory

**Likely causes:**
- Source path is incorrect or empty
- Terraform files are in a different directory
- terraform.source is pointing to wrong location

## ERROR: ParentFileNotFoundError on a file that sits beside the config

**Category:** configuration

`find_in_parent_folders` searches strictly *upward*. It starts at the parent of the referencing
config and never looks in that config's own directory, so pointing it at a sibling traverses to
the filesystem root and fails. The usual victim is `env.hcl` next to an environment's
`terragrunt.stack.hcl`.

```
Call to function "find_in_parent_folders" failed: ParentFileNotFoundError: Could not find a
env.hcl in any of the parent folders of .../dev/terragrunt.stack.hcl. Cause: Traversed all
the way to the root..
```

**Likely causes:**
- The target is a sibling of the referencing config, not an ancestor. `account.hcl` a
  directory or two up is fine; `env.hcl` in the same directory is not.
- The idiom was copied from a `root.hcl` include, where `find_in_parent_folders` is correct.
- The file genuinely is missing, or is named differently from what was passed.

**Solutions:**

```hcl
# Sibling: read it by relative path. A relative path resolves against the config file's own
# directory, not the shell's cwd, so this holds whether the command runs from that directory
# or from the repo root.
locals {
  env = read_terragrunt_config("env.hcl")
}

# Equivalent and more explicit, if you prefer an absolute path:
#   env = read_terragrunt_config("${get_terragrunt_dir()}/env.hcl")
```

Verified against terragrunt 1.1.3 on 2026-08-20.

## ERROR: Remote state configuration missing

**Category:** configuration

Remote state backend is not configured

**Likely causes:**
- remote_state block missing
- Backend type not specified
- Configuration incomplete

## ERROR: Required attribute missing

**Category:** configuration

Required configuration attribute is not provided

**Likely causes:**
- Mandatory attribute not specified
- Attribute removed in refactoring
- Version upgrade changed requirements

## ERROR: Syntax error in configuration

**Category:** configuration

HCL syntax error in terragrunt.hcl or .tf files

**Likely causes:**
- Missing closing braces or quotes
- Invalid HCL syntax
- Incorrect block structure

## ERROR: Type mismatch error

**Category:** configuration

Value type does not match expected type

**Likely causes:**
- String provided where number expected
- Incorrect collection type
- Type conversion failed

## ERROR: Undefined local reference

**Category:** configuration

Referenced local variable is not defined

**Likely causes:**
- Local variable not defined in locals block
- Typo in local variable name
- Local defined in different scope

## ERROR: Working directory error

**Category:** configuration

Cannot access or change to working directory

**Likely causes:**
- Directory does not exist
- Insufficient permissions
- Path is not a directory

## ERROR: Circular dependency detected

**Category:** dependency

Modules have circular dependencies which Terraform cannot resolve

**Likely causes:**
- Module A depends on Module B which depends on Module A
- Indirect circular dependency through multiple modules
- Output references create circular dependency

## ERROR: Circular module source reference

**Category:** dependency

Module source creates a circular reference

**Likely causes:**
- Module source points to itself
- Indirect circular reference through includes
- Parent module depends on child

## ERROR: Could not download source

**Category:** dependency

Failed to download module source code

**Likely causes:**
- Network connectivity issues
- Invalid or inaccessible URL
- Authentication required but not provided

## ERROR: Git authentication failed

**Category:** dependency

Failed to authenticate with Git repository

**Likely causes:**
- SSH key not configured
- Git credentials expired or invalid
- Repository requires authentication

## ERROR: Git ref not found

**Category:** dependency

Specified Git tag or branch does not exist

**Likely causes:**
- Tag or branch name is incorrect
- Tag/branch was deleted
- Typo in ref parameter

## ERROR: Local module path invalid

**Category:** dependency

Local module path is invalid or inaccessible

**Likely causes:**
- Relative path incorrect
- Module directory moved or deleted
- Path traversal issues

## ERROR: Module archive extraction error

**Category:** dependency

Failed to extract module archive

**Likely causes:**
- Corrupted download
- Unsupported archive format
- Insufficient disk space

## ERROR: Module cache corrupted

**Category:** dependency

Module cache is corrupted

**Likely causes:**
- Incomplete download
- Disk corruption
- Cache directory permissions

**Solutions:**

```bash
terragrunt clear-cache
```

## ERROR: Module checksum mismatch

**Category:** dependency

Downloaded module checksum does not match expected value

**Likely causes:**
- Module was modified after download
- Network corruption during download
- Lock file out of sync

## ERROR: Module not found

**Category:** dependency

Terragrunt cannot locate a referenced module

**Likely causes:**
- Module path is incorrect
- Module does not exist at specified location
- Git repository or URL is inaccessible

## ERROR: Module registry unavailable

**Category:** dependency

Cannot access Terraform module registry

**Likely causes:**
- Network connectivity issues
- Registry is down
- Firewall blocking registry access

## ERROR: Module subdirectory not found

**Category:** dependency

Specified subdirectory does not exist in module source

**Likely causes:**
- Subdirectory path is incorrect
- Path changed in module version
- Double slashes in path

## ERROR: Module version not found

**Category:** dependency

No module version matches the specified constraint

**Likely causes:**
- Version constraint too strict
- Requested version does not exist
- Module has no published versions

## ERROR: Connection refused

**Category:** network

Cannot establish connection to remote service

**Likely causes:**
- Service is not running
- Wrong host or port
- Firewall blocking connection

## ERROR: Network timeout

**Category:** network

Network operation timed out

**Likely causes:**
- Network connectivity issues
- Firewall blocking connection
- Service endpoint is slow or unavailable

## ERROR: Backend configuration changed

**Category:** state

The backend configuration has changed and state needs to be migrated

**Likely causes:**
- Backend bucket/container changed
- Backend region changed
- Backend configuration was modified

**Solutions:**

```bash
terragrunt init -reconfigure
```
```bash
terragrunt init -migrate-state
```

## ERROR: Error acquiring state lock

**Category:** state

Unable to acquire state lock, usually because another process has it

**Likely causes:**
- Another Terragrunt/Terraform process is running
- Previous process crashed without releasing lock
- Lock file was not cleaned up properly

**Solutions:**

```bash
terragrunt force-unlock <LOCK_ID>
```

## ERROR: Failed to get existing workspaces

**Category:** state

Cannot retrieve or access Terraform workspace

**Likely causes:**
- Backend is not properly initialized
- Workspace does not exist
- Backend credentials are invalid

**Solutions:**

```bash
terragrunt init
```
```bash
terragrunt workspace list
```
```bash
terragrunt workspace new <name>
```

## ERROR: Provider not found

**Category:** terraform

Required Terraform provider is not installed

**Likely causes:**
- Provider not specified in required_providers
- Provider version constraint cannot be satisfied
- Provider registry is inaccessible

**Solutions:**

```bash
terragrunt init
```

## ERROR: Provider version constraint

**Category:** terraform

Provider version does not meet requirements

**Likely causes:**
- Installed provider version is too old or too new
- Version constraint is too strict
- Lock file specifies different version

**Solutions:**

```bash
terragrunt init -upgrade
```

## ERROR: Terraform version constraint not met

**Category:** terraform

The installed Terraform version does not meet requirements

**Likely causes:**
- Wrong Terraform version installed
- Version constraint in configuration is too strict
- Using outdated Terraform binary

**Solutions:**

```bash
terraform version
```
