# Terragrunt Built-in Functions

> Source: curated data harvested from omattsson/terragrunt-mcp-server, restructured for grep-based lookup.
> Content spot-checked against docs.terragrunt.com at **v1.1.0** (2026-07-01); reviewed against the **v1.1.1** release notes (2026-07-14) on 2026-07-29 with no changes required — v1.1.1 was bug-fix only, and its two new experiments touch the `terraform` block (see hcl-blocks.md). Reviewed against the **v1.1.2** release notes (2026-07-29) on 2026-08-05, again with no changes required: v1.1.2 made `find_in_parent_folders()` 7–10x faster by checking only the filename the call names rather than also probing for default config filenames at every level, but its signature, parameters and documented behaviour are unchanged. Nothing in this file claimed a cost for it, so nothing needed retracting. Flag and avoid any pre-1.0 idioms.

Lookup: `grep -n '^## FUNCTION:' functions.md` to list; `grep -A 30 '^## FUNCTION: get_env' functions.md` to read one.

## Categories
- **aws**: get_aws_account_id, get_aws_account_alias, get_aws_caller_identity_arn, get_aws_caller_identity_user_id
- **environment**: get_env, get_platform
- **execution**: run_cmd
- **file**: read_terragrunt_config, read_tfvars_file, sops_decrypt_file, mark_as_read
- **path**: find_in_parent_folders, path_relative_to_include, path_relative_from_include, get_terragrunt_dir, get_working_dir, get_parent_terragrunt_dir, get_original_terragrunt_dir, get_repo_root, get_path_from_repo_root, get_path_to_repo_root
- **terraform**: get_terraform_commands_that_need_vars, get_terraform_commands_that_need_input, get_terraform_commands_that_need_locking, get_terraform_commands_that_need_parallelism, get_terraform_command, get_terraform_cli_args
- **utility**: get_terragrunt_source_cli_flag, get_default_retryable_errors, constraint_check

## FUNCTION: get_aws_account_alias

**Signature:** `get_aws_account_alias()`  |  **Returns:** string  |  **Category:** aws

Returns the AWS account alias associated with the current credentials. Returns an empty string if no alias is set. Note: The value can change during HCL parsing.

*Pass account alias to Terraform*
```hcl
inputs = {
  account_alias = get_aws_account_alias()
}
```

Related: get_aws_account_id, get_aws_caller_identity_arn

## FUNCTION: get_aws_account_id

**Signature:** `get_aws_account_id()`  |  **Returns:** string  |  **Category:** aws

Returns the AWS account ID associated with the current set of credentials. Note: The value can change during HCL parsing, for example after evaluation of the iam_role attribute.

*Create account-specific bucket name*
```hcl
remote_state {
  config = {
    bucket = "mycompany-${get_aws_account_id()}"
  }
}
```

*Load account-specific variables*
```hcl
terraform {
  extra_arguments "account_vars" {
    arguments = ["-var-file=${get_aws_account_id()}.tfvars"]
  }
}
```

Related: get_aws_account_alias, get_aws_caller_identity_arn, get_aws_caller_identity_user_id

## FUNCTION: get_aws_caller_identity_arn

**Signature:** `get_aws_caller_identity_arn()`  |  **Returns:** string  |  **Category:** aws

Returns the ARN of the AWS identity associated with the current credentials. Note: The value can change during HCL parsing, for example after evaluation of the iam_role attribute.

*Pass caller ARN to Terraform*
```hcl
inputs = {
  caller_arn = get_aws_caller_identity_arn()
}
```

Related: get_aws_account_id, get_aws_caller_identity_user_id

## FUNCTION: get_aws_caller_identity_user_id

**Signature:** `get_aws_caller_identity_user_id()`  |  **Returns:** string  |  **Category:** aws

Returns the User ID of the AWS identity associated with the current credentials. Note: The value can change during HCL parsing, for example after evaluation of the iam_role attribute.

*Pass caller user ID to Terraform*
```hcl
inputs = {
  caller_user_id = get_aws_caller_identity_user_id()
}
```

Related: get_aws_account_id, get_aws_caller_identity_arn

## FUNCTION: get_env

**Signature:** `get_env(name, [default])`  |  **Returns:** string  |  **Category:** environment

Returns the value of the environment variable with the given name. If the variable is not set and no default is provided, throws an error. Tip: OpenTofu/Terraform reads TF_VAR_* environment variables automatically.

**Parameters:**
- `name` (string, required): The name of the environment variable
- `default` (string, optional): Default value if the variable is not set

*Read required environment variable*
```hcl
remote_state {
  config = {
    bucket = get_env("TG_BUCKET")
  }
}
```

*Read environment variable with default*
```hcl
locals {
  env = get_env("ENVIRONMENT", "dev")
}
```

Related: get_platform

## FUNCTION: get_platform

**Signature:** `get_platform()`  |  **Returns:** string  |  **Category:** environment

Returns the current operating system. Useful for platform-specific configurations. Returns values like "darwin", "linux", "windows", "freebsd".

*Pass platform to Terraform*
```hcl
inputs = {
  platform = get_platform()
}
```

*Conditional logic based on OS*
```hcl
locals {
  is_mac = get_platform() == "darwin"
}
```

Related: get_env

## FUNCTION: run_cmd

**Signature:** `run_cmd([flags], command, ...args)`  |  **Returns:** string  |  **Category:** execution

Runs a shell command and returns stdout as the result. Executes in the same folder as the terragrunt.hcl file. Supports special flags: --terragrunt-quiet (suppress output), --terragrunt-global-cache (cache globally), --terragrunt-no-cache (disable caching). Results are cached by default based on directory and command.

**Parameters:**
- `flags` (string, optional): Optional flags: --terragrunt-quiet, --terragrunt-global-cache, --terragrunt-no-cache
- `command` (string, required): The command to execute
- `args` (string..., optional): Arguments to pass to the command

*Run script to get dynamic value*
```hcl
remote_state {
  config = {
    bucket = run_cmd("./get_bucket_name.sh")
  }
}
```

*Run command with suppressed output for secrets*
```hcl
locals {
  secret = run_cmd("--terragrunt-quiet", "./decrypt.sh", "secret_name")
}
```

Related: get_env

## FUNCTION: mark_as_read

**Signature:** `mark_as_read(file_path)`  |  **Returns:** string  |  **Category:** file

Marks a file as read for the --queue-include-units-reading flag. Use this when a file is read by external tools (like Terraform) but Terragrunt needs to track the dependency. Requires absolute path.

**Parameters:**
- `file_path` (string, required): Absolute path to the file to mark as read

*Mark file as read for queue inclusion*
```hcl
locals {
  filename = mark_as_read("/path/to/config.txt")
}
inputs = {
  config_file = local.filename
}
```

*Mark multiple files as read*
```hcl
locals {
  files = [for f in fileset("./config", "*.yaml") : file(mark_as_read(abspath("${get_terragrunt_dir()}/config/${f}")))]
}
```

Related: read_terragrunt_config

## FUNCTION: read_terragrunt_config

**Signature:** `read_terragrunt_config(config_path, [default_val])`  |  **Returns:** map  |  **Category:** file

Parses a Terragrunt config file and returns a map of its contents. Exposes all blocks and attributes including locals, inputs, and dependency outputs. Also supports reading terragrunt.stack.hcl and terragrunt.values.hcl files.

**Parameters:**
- `config_path` (string, required): Path to the terragrunt config file to read
- `default_val` (any, optional): Default value to return if the file does not exist

*Read and merge common configuration*
```hcl
locals {
  common = read_terragrunt_config(find_in_parent_folders("common.hcl"))
}
inputs = merge(local.common.inputs, { })
```

*Access dependency outputs from another config*
```hcl
locals {
  deps = read_terragrunt_config("common_deps.hcl")
}
inputs = {
  vpc_id = local.deps.dependency.vpc.outputs.vpc_id
}
```

Related: find_in_parent_folders, read_tfvars_file

## FUNCTION: read_tfvars_file

**Signature:** `read_tfvars_file(file_path)`  |  **Returns:** map  |  **Category:** file

Reads a .tfvars or .tfvars.json file and returns a map of the variables defined in it. Useful for incorporating existing Terraform variable files.

**Parameters:**
- `file_path` (string, required): Path to the .tfvars or .tfvars.json file

*Read and merge tfvars file*
```hcl
locals {
  vars = read_tfvars_file("common.tfvars")
}
inputs = merge(local.vars, { })
```

*Use tfvars for backend configuration*
```hcl
locals {
  backend = read_tfvars_file("backend.tfvars")
}
remote_state {
  config = {
    region = local.backend.region
  }
}
```

Related: read_terragrunt_config

## FUNCTION: sops_decrypt_file

**Signature:** `sops_decrypt_file(file_path)`  |  **Returns:** string  |  **Category:** file

Decrypts a file encrypted with SOPS (Secrets OPerationS). Supports YAML, JSON, ENV, INI, and raw text formats. Requires SOPS to be configured with appropriate key management (AWS KMS, GCP KMS, Azure Key Vault, HashiCorp Vault, or PGP).

**Parameters:**
- `file_path` (string, required): Path to the SOPS-encrypted file

*Decrypt and parse YAML secrets*
```hcl
locals {
  secrets = yamldecode(sops_decrypt_file("secrets.yaml"))
}
inputs = merge(local.secrets, { })
```

*Decrypt JSON with fallback*
```hcl
locals {
  secrets = try(jsondecode(sops_decrypt_file("secrets.json")), {})
}
```

Related: read_terragrunt_config

## FUNCTION: find_in_parent_folders

**Signature:** `find_in_parent_folders(name, [fallback])`  |  **Returns:** string  |  **Category:** path

Searches up the directory tree from the current terragrunt.hcl file and returns the absolute path to the first file in a parent folder with a given name. If no file is found and no fallback is provided, exits with an error.

**Parameters:**
- `name` (string, required): The filename to search for in parent directories
- `fallback` (string, optional): Value to return if the file is not found (prevents error)

*Find and include root configuration*
```hcl
include "root" {
  path = find_in_parent_folders("root.hcl")
}
```

*Find env config with fallback if not found*
```hcl
find_in_parent_folders("env.hcl", "fallback.hcl")
```

Related: get_terragrunt_dir, get_parent_terragrunt_dir, read_terragrunt_config

## FUNCTION: get_original_terragrunt_dir

**Signature:** `get_original_terragrunt_dir()`  |  **Returns:** string  |  **Category:** path

Returns the directory where the original Terragrunt configuration file lives. Primarily useful when one config is being read from another via read_terragrunt_config().

*Get the original terragrunt.hcl directory when reading configs*
```hcl
locals {
  original_dir = get_original_terragrunt_dir()
}
```

Related: get_terragrunt_dir, get_parent_terragrunt_dir, read_terragrunt_config

## FUNCTION: get_parent_terragrunt_dir

**Signature:** `get_parent_terragrunt_dir([name])`  |  **Returns:** string  |  **Category:** path

Returns the absolute directory where the Terragrunt parent configuration file lives. Similar to get_terragrunt_dir() but returns the root instead of the leaf of your terragrunt configurations.

**Parameters:**
- `name` (string, optional): The name of the include block when multiple includes exist

*Reference common vars from parent directory*
```hcl
arguments = [
  "-var-file=${get_parent_terragrunt_dir()}/common.tfvars"
]
```

*Reference modules from named parent include*
```hcl
terraform {
  source = "${get_parent_terragrunt_dir(\"root\")}/modules/vpc"
}
```

Related: get_terragrunt_dir, get_original_terragrunt_dir, find_in_parent_folders

## FUNCTION: get_path_from_repo_root

**Signature:** `get_path_from_repo_root()`  |  **Returns:** string  |  **Category:** path

Returns the path from the root of the Git repository to the current directory. Errors if the file is not in a Git repository.

*Generate state key based on repo path*
```hcl
remote_state {
  config = {
    key = "${get_path_from_repo_root()}/terraform.tfstate"
  }
}
```

Related: get_repo_root, get_path_to_repo_root, path_relative_to_include

## FUNCTION: get_path_to_repo_root

**Signature:** `get_path_to_repo_root()`  |  **Returns:** string  |  **Category:** path

Returns the relative path from the current directory to the root of the Git repository. Errors if the file is not in a Git repository.

*Reference modules relative to repo root*
```hcl
terraform {
  source = "${get_path_to_repo_root()}//modules/example"
}
```

> **Prefer a config-hierarchy anchor to a git anchor.** Both this and `get_repo_root()` walk up
> to `.git`, so they resolve to the wrong place — or error outright — when the working tree is
> an exported artifact with no `.git`, when CI checks out only the infrastructure subtree, or
> when the git root sits above the infrastructure root in a monorepo. The failure is
> environment-dependent: it works on your laptop and breaks in the pipeline.
>
> Anchor to a marker file that always ships with the configs instead:
> `dirname(find_in_parent_folders("root.hcl"))`, or `get_parent_terragrunt_dir("root")` in a
> unit that includes the root. For a path *within* the hierarchy — a state key, a generated
> file path — use `path_relative_to_include()`. Full reasoning in
> `architecture-patterns.md`, `## Path anchoring: marker files over git`.

Related: get_repo_root, get_path_from_repo_root, path_relative_to_include, get_parent_terragrunt_dir

## FUNCTION: get_repo_root

**Signature:** `get_repo_root()`  |  **Returns:** string  |  **Category:** path

**CI/CD caveat:** git-anchored (walks up to `.git`). Breaks on exported trees without
`.git`, subtree-only checkouts, and monorepos where git root != infrastructure root.
Prefer `dirname(find_in_parent_folders("root.hcl"))` or `get_parent_terragrunt_dir("root")`
for portable path anchoring.

Returns the absolute path to the root of the Git repository. Errors if the file is not located in a Git repository.

*Reference files from repository root*
```hcl
inputs = {
  config_path = "${get_repo_root()}/config/app.conf"
}
```

Related: get_path_from_repo_root, get_path_to_repo_root

## FUNCTION: get_terragrunt_dir

**Signature:** `get_terragrunt_dir()`  |  **Returns:** string  |  **Category:** path

Returns the directory where the Terragrunt configuration file (by default terragrunt.hcl) lives. Useful for constructing paths relative to your Terragrunt configuration.

*Reference files relative to terragrunt.hcl*
```hcl
arguments = [
  "-var-file=${get_terragrunt_dir()}/../common.tfvars"
]
```

*Reference local modules*
```hcl
terraform {
  source = "${get_terragrunt_dir()}/../modules//vpc"
}
```

Related: get_parent_terragrunt_dir, get_original_terragrunt_dir, get_working_dir

## FUNCTION: get_working_dir

**Signature:** `get_working_dir()`  |  **Returns:** string  |  **Category:** path

Returns the absolute path where Terragrunt runs OpenTofu/Terraform commands. Useful for managing file substitutions in the temporary working directory.

*Get the Terraform working directory*
```hcl
locals {
  working_dir = get_working_dir()
}
```

Related: get_terragrunt_dir, get_original_terragrunt_dir

## FUNCTION: path_relative_from_include

**Signature:** `path_relative_from_include([name])`  |  **Returns:** string  |  **Category:** path

Returns the relative path from the path specified in the include block to the current terragrunt.hcl file. This is the counterpart of path_relative_to_include().

**Parameters:**
- `name` (string, optional): The name of the include block to use when multiple include blocks exist

*Construct source path relative to include*
```hcl
terraform {
  source = "${path_relative_from_include()}/../sources//${path_relative_to_include()}"
}
```

*Reference common tfvars from root*
```hcl
arguments = [
  "-var-file=${get_terragrunt_dir()}/${path_relative_from_include()}/common.tfvars"
]
```

Related: path_relative_to_include, get_terragrunt_dir, get_parent_terragrunt_dir

## FUNCTION: path_relative_to_include

**Signature:** `path_relative_to_include([name])`  |  **Returns:** string  |  **Category:** path

Returns the relative path between the current terragrunt.hcl file and the path specified in its include block. Useful for generating unique state keys based on directory structure.

**Parameters:**
- `name` (string, optional): The name of the include block to use when multiple include blocks exist

*Generate unique state key based on directory path*
```hcl
remote_state {
  backend = "s3"
  config = {
    key = "${path_relative_to_include()}/terraform.tfstate"
  }
}
```

*Get path relative to specific named include*
```hcl
path_relative_to_include("root")
```

Related: path_relative_from_include, find_in_parent_folders, get_terragrunt_dir

## FUNCTION: get_terraform_cli_args

**Signature:** `get_terraform_cli_args()`  |  **Returns:** list(string)  |  **Category:** terraform

Returns the CLI arguments passed to the current OpenTofu/Terraform command. Useful for inspecting or passing through arguments.

*Pass CLI args to Terraform*
```hcl
inputs = {
  cli_args = get_terraform_cli_args()
}
```

Related: get_terraform_command

## FUNCTION: get_terraform_command

**Signature:** `get_terraform_command()`  |  **Returns:** string  |  **Category:** terraform

Returns the current OpenTofu/Terraform command being executed (e.g., "apply", "plan", "init"). Useful for conditional logic based on the command.

*Pass current command to Terraform*
```hcl
inputs = {
  current_command = get_terraform_command()
}
```

*Conditional logic based on command*
```hcl
locals {
  is_apply = get_terraform_command() == "apply"
}
```

Related: get_terraform_cli_args

## FUNCTION: get_terraform_commands_that_need_input

**Signature:** `get_terraform_commands_that_need_input()`  |  **Returns:** list(string)  |  **Category:** terraform

Returns the list of OpenTofu/Terraform commands that accept the -input=(true or false) parameter. Use this to disable interactive input in CI/CD pipelines.

*Disable interactive input for all relevant commands*
```hcl
terraform {
  extra_arguments "disable_input" {
    commands = get_terraform_commands_that_need_input()
    arguments = ["-input=false"]
  }
}
```

Related: get_terraform_commands_that_need_vars, get_terraform_commands_that_need_locking

## FUNCTION: get_terraform_commands_that_need_locking

**Signature:** `get_terraform_commands_that_need_locking()`  |  **Returns:** list(string)  |  **Category:** terraform

Returns the list of OpenTofu/Terraform commands that accept the -lock-timeout parameter. Use this to configure lock timeout for state operations.

*Set lock timeout for all locking commands*
```hcl
terraform {
  extra_arguments "retry_lock" {
    commands = get_terraform_commands_that_need_locking()
    arguments = ["-lock-timeout=20m"]
  }
}
```

Related: get_terraform_commands_that_need_vars, get_terraform_commands_that_need_parallelism

## FUNCTION: get_terraform_commands_that_need_parallelism

**Signature:** `get_terraform_commands_that_need_parallelism()`  |  **Returns:** list(string)  |  **Category:** terraform

Returns the list of OpenTofu/Terraform commands that accept the -parallelism parameter. Use this to limit concurrent operations.

*Limit parallelism for all relevant commands*
```hcl
terraform {
  extra_arguments "parallelism" {
    commands = get_terraform_commands_that_need_parallelism()
    arguments = ["-parallelism=5"]
  }
}
```

Related: get_terraform_commands_that_need_vars, get_terraform_commands_that_need_locking

## FUNCTION: get_terraform_commands_that_need_vars

**Signature:** `get_terraform_commands_that_need_vars()`  |  **Returns:** list(string)  |  **Category:** terraform

Returns the list of OpenTofu/Terraform commands that accept -var and -var-file parameters. Use this in extra_arguments blocks to apply variable files only to relevant commands.

*Apply var file to all relevant commands*
```hcl
terraform {
  extra_arguments "common_vars" {
    commands = get_terraform_commands_that_need_vars()
    arguments = ["-var-file=common.tfvars"]
  }
}
```

Related: get_terraform_commands_that_need_input, get_terraform_commands_that_need_locking, get_terraform_commands_that_need_parallelism

## FUNCTION: constraint_check

**Signature:** `constraint_check(version, constraint)`  |  **Returns:** bool  |  **Category:** utility

Checks if a version satisfies a constraint. Useful for conditional logic based on module versions. Supports the same constraint syntax as terragrunt_version_constraint and terraform_version_constraint.

**Parameters:**
- `version` (string, required): The version to check (e.g., "1.2.3")
- `constraint` (string, required): The constraint to check against (e.g., ">= 2.0.0")

*Conditional inputs based on module version*
```hcl
locals {
  module_version = "2.1.0"
  needs_v2 = constraint_check(local.module_version, ">= 2.0.0")
}
inputs = local.needs_v2 ? { new_input = "value" } : { old_input = "value" }
```

*Use with feature flags*
```hcl
feature "module_version" {
  default = "1.2.3"
}
locals {
  is_v2 = constraint_check(feature.module_version.value, ">= 2.0.0")
}
```

## FUNCTION: get_default_retryable_errors

**Signature:** `get_default_retryable_errors()`  |  **Returns:** list(string)  |  **Category:** utility

Returns the default list of retryable error patterns that Terragrunt uses for transient failures. Use in the errors block to seed retry configuration with sensible defaults.

*Use default retryable errors*
```hcl
errors {
  retry "default_errors" {
    retryable_errors = get_default_retryable_errors()
    max_attempts = 3
    sleep_interval_sec = 5
  }
}
```

*Combine default and custom retryable errors*
```hcl
errors {
  retry "combined" {
    retryable_errors = concat(get_default_retryable_errors(), [".*my custom error.*"])
    max_attempts = 5
  }
}
```

## FUNCTION: get_terragrunt_source_cli_flag

**Signature:** `get_terragrunt_source_cli_flag()`  |  **Returns:** string  |  **Category:** utility

Returns the value passed via --source CLI flag or TG_SOURCE environment variable. Returns empty string if not set. Useful for local development overrides and conditional logic.

*Detect local development mode*
```hcl
locals {
  is_local_dev = get_terragrunt_source_cli_flag() != ""
}
```

*Load mocks from local source*
```hcl
dependency "vpc" {
  mock_outputs = get_terragrunt_source_cli_flag() != "" ? jsondecode(file("${get_terragrunt_source_cli_flag()}/mocks/vpc.json")) : {}
}
```

Related: get_env

## FUNCTION: mark_glob_as_read

**Signature:** `mark_glob_as_read([boundary,] pattern)`  |  **Returns:** list(string)  |  **Category:** read-tracking  |  **v1.1.0+**

Expands `pattern` (gobwas/glob syntax: `*` within a segment, `**` across segments, `?`,
`[abc]`, `{a,b}`; `\` escapes) and marks every matching file as **read** by the unit, so a
change to any of them selects the unit through reading-based filters (`--filter 'reading=…'`,
`--queue-include-units-reading`). Returns the matched absolute paths, so it composes with
other expressions. Relative patterns resolve against the current working directory. Added in
**v1.1.0** (GA; was the `mark-many-as-read` experiment) — do NOT emit for repos pinned to ≤1.0.x.

Use it when a unit consumes files indirectly (via `run_cmd`, `templatefile`, a shared helper
module, etc.) and you want changes to any of them to trigger the unit in change-based CI.

*Mark a directory of YAML configs as read*
```hcl
locals {
  configs = mark_glob_as_read("${get_terragrunt_dir()}/config/{*.yaml,**/*.yaml}")
}
```

**Boundary guard.** Expansion is confined to a boundary directory — by default the enclosing
Git repo root (unset outside a repo); a walk that would start outside it errors instead of
expanding. This stops a pattern interpolated from an empty value (`"${local.dir}/{*.yaml}"` →
`/{*.yaml}`) from walking the filesystem. Note HCL evaluates *both* branches of a `? :`, so a
conditional does not prevent this — wrap in `try(..., [])` to fall back. Pass a leading
`--terragrunt-boundary=<path>` argument to set it explicitly:
```hcl
locals {
  scoped     = mark_glob_as_read("--terragrunt-boundary=/etc/terragrunt", "/etc/terragrunt/{*.yaml}")
  everything = mark_glob_as_read("--terragrunt-boundary=/", "/{*.yaml}")
  safe       = sort(try(mark_glob_as_read("${local.dir}/{*.yaml,*.yml}"), []))
}
```

Related: get_terragrunt_dir, read_terragrunt_config
