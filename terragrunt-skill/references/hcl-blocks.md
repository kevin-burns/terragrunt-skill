# Terragrunt HCL Block Reference

> Source: curated data harvested from omattsson/terragrunt-mcp-server, restructured for grep-based lookup.
> Content spot-checked against docs.terragrunt.com at **v1.1.0** (2026-07-01), updated for **v1.1.1** (2026-07-14), then reviewed against the **v1.1.2** release notes (2026-07-29) on 2026-08-05 — one change: `iam_role` carries a v1.1.1 regression warning (see `## ATTRIBUTE: iam_role`). Flag and avoid any pre-1.0 idioms.
>
> **Audited 2026-08-19** against snapshots of `/reference/hcl/blocks/` and
> `/reference/hcl/attributes/` (kept in `evals/snapshots/`). Four pre-1.0 blocks removed
> (`retryable_errors`, `retry_max_attempts`, `retry_sleep_interval_sec`, `skip`); five added
> that were missing entirely (`errors`, `exclude`, `catalog`, `engine`, `feature`); four
> attributes added to `terraform`; ten entries retagged from `BLOCK` to `ATTRIBUTE`.
> **Every version number in this file is UNVERIFIED against the reference pages** — they state
> no versions at all. The gates come from release notes, which were not re-snapshotted. Treat a
> version claim here as a lead, not a fact, and check `scripts/preflight.py` for what the local
> binary actually supports.

Lookup: `grep -n '^## BLOCK:' hcl-blocks.md` for blocks, `grep -n '^## ATTRIBUTE:'` for
attributes, or `grep -nE '^## (BLOCK|ATTRIBUTE):'` for both.

> **Two headings, deliberately.** Terragrunt's own reference splits these: blocks live on
> `/reference/hcl/blocks/` and take braces; attributes live on `/reference/hcl/attributes/` and
> take `=`. Until 2026-08-19 this file labelled all of them `## BLOCK:`, so grepping for a block
> returned attributes and the file disagreed with its own source's taxonomy. The content was
> correct throughout; only the label was wrong.

## Contents

**Blocks** (`grep '^## BLOCK:'`) — take braces:
- autoinclude (terragrunt.stack.hcl, v1.1.0+)
- catalog
- dependencies
- dependency
- engine (experimental; stub upstream)
- errors (retry / ignore — replaces pre-1.0 retryable_errors)
- exclude (replaces the pre-1.0 skip attribute)
- feature (flags; the producer for exclude's `if`)
- generate
- include
- locals
- remote_state
- stack (terragrunt.stack.hcl)
- terraform
- unit (terragrunt.stack.hcl)

**Attributes** (`grep '^## ATTRIBUTE:'`) — take `=`:
- download_dir
- iam_assume_role_duration
- iam_assume_role_session_name
- iam_role
- iam_web_identity_token
- inputs
- prevent_destroy
- terraform_binary
- terraform_version_constraint
- terragrunt_version_constraint

## BLOCK: dependencies

**Dependencies Block**  |  Category: modules

Shorthand for declaring multiple dependencies when you only need ordering (not outputs). Use this when you want Terragrunt to apply modules in a specific order but don't need to reference their outputs.

**Syntax:**
```hcl
dependencies { ... }
```

**Attributes:**
- `paths` (list, required): List of paths to dependency modules.

*Simple dependency ordering*
```hcl
dependencies {
  paths = ["../vpc", "../security-groups"]
}
```

*Combined with dependency block*
```hcl
# Use dependencies for ordering only
dependencies {
  paths = ["../iam"]
}

# Use dependency when you need outputs
dependency "vpc" {
  config_path = "../vpc"
}

inputs = {
  vpc_id = dependency.vpc.outputs.vpc_id
}
```

Related: dependency

## BLOCK: dependency

**Dependency Block**  |  Category: modules

Declares a dependency on another Terragrunt module, allowing access to its outputs. Terragrunt ensures dependencies are applied in the correct order when using `run --all`.

**Syntax:**
```hcl
dependency "<label>" { ... }
```

**Attributes:**
- `config_path` (string, required): Relative or absolute path to the dependency's terragrunt.hcl directory.
- `enabled` (boolean): Whether this dependency is enabled. Useful for conditional dependencies.
- `skip_outputs` (boolean): Skip fetching outputs from this dependency (useful for destroy operations).
- `mock_outputs` (map): Mock output values to use when the dependency hasn't been applied yet.
  **v1.1.3 widened when these actually apply, twice.** With
  `--dependency-fetch-output-from-state`, Terragrunt previously fell back to mocks only when
  the state *object* was missing, not when the state *bucket* did not exist — so a
  `dependency` on an environment that had never been bootstrapped failed instead of mocking.
  A missing bucket is now treated the same as a missing object. Separately, a `dependency`
  whose `config_path` points at a `terragrunt.stack.hcl` directory used to fail when any unit
  in that stack had no state, even with `mock_outputs` declared; it now falls back per unit,
  so a partially applied stack resolves real outputs for applied units and mocks for the
  rest. **Mocks for a stack dependency are keyed by unit name, so `mock_outputs` must be a
  map or object** — any other type is now reported directly rather than silently leaving
  those units out of the stack outputs. Both need v1.1.3+.
- `mock_outputs_allowed_terraform_commands` (list): Terraform commands for which `mock_outputs` are allowed. If the command being run is NOT in this list and the dependency has no real outputs yet, Terragrunt errors instead of using mocks. A common set is `["init", "validate", "plan", "destroy"]` — include `destroy` so teardown still works once a dependency has already been removed.
- `mock_outputs_merge_strategy_with_state` (string): how mock values combine with real state outputs. One of:
  - `"no_merge"` (default) — if the dependency has any real outputs, mocks are ignored entirely; mocks are used only when there are no outputs at all.
  - `"shallow"` — real state wins per top-level key, and mocks backfill keys the applied state doesn't have yet (e.g. a new output added to the module since its last apply, so `plan` doesn't fail on a missing key).
  - `"deep_map_only"` — like shallow but recurses into nested maps; lists are NOT merged.
  Replaces the deprecated boolean `mock_outputs_merge_with_state`.

Only `dependency.<name>.outputs` is available — the old `dependency.<name>.inputs`
accessor has been removed. A `dependency` block both creates a DAG ordering edge **and**
exposes outputs; use `dependencies` (below) when you need ordering without outputs.

*Simple dependency on VPC module*
```hcl
dependency "vpc" {
  config_path = "../vpc"
}

inputs = {
  vpc_id = dependency.vpc.outputs.vpc_id
}
```

*Dependency with mock outputs for plan/validate*
```hcl
dependency "vpc" {
  config_path = "../vpc"

  mock_outputs = {
    vpc_id            = "vpc-mock12345"
    private_subnet_ids = ["subnet-mock1", "subnet-mock2"]
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}
```

*Mocks across more commands, backfilling newly-added outputs from state*
```hcl
dependency "vpc" {
  config_path = "../vpc"

  mock_outputs = {
    vpc_id             = "vpc-mock12345"
    private_subnet_ids = ["subnet-mock1", "subnet-mock2"]
  }
  # Allow mocks for these commands; if the running command isn't listed AND there
  # are no real outputs yet, Terragrunt errors instead of mocking. `destroy` is
  # included so teardown still works once the dependency is already gone.
  mock_outputs_allowed_terraform_commands = ["init", "validate", "plan", "destroy"]
  # "shallow": prefer real state per key, let mocks backfill any key the applied
  # state lacks (e.g. an output added to the module since the last apply).
  mock_outputs_merge_strategy_with_state = "shallow"
}
```

Related: dependencies, inputs

## ATTRIBUTE: download_dir

**Download Directory Attribute**  |  Category: terraform

Custom directory where Terragrunt downloads and caches Terraform modules. Defaults to a temporary directory.

**Syntax:**
```hcl
download_dir = "<path>"
```

**Attributes:**
- `download_dir` (string): Path to download directory.

*Use custom cache directory*
```hcl
download_dir = "${get_env("HOME")}/.terragrunt-cache"
```

Related: terraform

## BLOCK: generate

**Generate Block**  |  Category: generation

Generates a file in the Terraform working directory before Terraform runs. Commonly used to generate provider configurations, backend blocks, or shared variable files.

**Syntax:**
```hcl
generate "<label>" { ... }
```

**Attributes:**
- `path` (string, required): Path to the file to generate (relative to the Terraform working directory).
- `if_exists` (string): What to do if the file already exists — `overwrite`, `overwrite_terragrunt`, `skip`, or `error`.
- `if_disabled` (string): What to do with an existing generated file when `disable = true` — `remove`, `remove_terragrunt`, or `skip` (default `skip`).
- `contents` (string, required): The content to write to the file. Supports heredoc syntax.
- `comment_prefix` (string): Prefix for the auto-generated comment (default `#`). Empty string disables the comment.
- `disable_signature` (boolean, default `false`): Disable the "Generated by Terragrunt" signature in the file.
- `hcl_fmt` (boolean, default `true`): When `false`, skip HCL formatting of generated `.tf`/`.hcl`/`.tofu` files.
- `disable` (boolean): Disable this generate block.
- `mutable` (boolean, default `false`): **Experiment `mutable-generate`, v1.1.3+.** With the
  experiment on, a `generate` block's contents are stored in the CAS and the file at `path`
  is a read-only link to that stored copy, so a block inherited by several hundred units
  costs one copy in `.terragrunt-cache` rather than several hundred. `mutable = true` gives
  this block a writable file of its own instead. **Setting it without the experiment is an
  error, and versions before v1.1.3 reject the attribute outright.** `--no-cas` writes
  generated files directly and `mutable` then has no effect.
  **`mutable` EXISTS ON THREE DIFFERENT BLOCKS. Check which one you are looking at.**

  | block | what it means | gate |
  |---|---|---|
  | `generate` (here) | the generated file is an ordinary writable file | experiment `mutable-generate` |
  | `terraform` | CAS content is copied and the working tree is editable, instead of materialised read-only | none |
  | `unit` | the same read-only-link vs writable-copy choice, for a unit in a stack | none, GA since v1.1.0 |

  Default is `false` everywhere. The `terraform` one has no effect when CAS is not used to
  fetch the source. An earlier revision of this file warned about two of the three, which is
  worse than warning about none — it implies the list is complete.

*Generate AWS provider*
```hcl
generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
provider "aws" {
  region = "${local.region}"

  default_tags {
    tags = {
      Environment = "${local.environment}"
      ManagedBy   = "Terragrunt"
    }
  }
}
EOF
}
```

*Generate required providers*
```hcl
generate "versions" {
  path      = "versions.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
EOF
}
```

Related: terraform, remote_state

## ATTRIBUTE: iam_assume_role_duration

**IAM Assume Role Duration Attribute**  |  Category: iam

Duration in seconds for the assumed IAM role session. Defaults to 3600 (1 hour).

**Syntax:**
```hcl
iam_assume_role_duration = <number>
```

**Attributes:**
- `iam_assume_role_duration` (number): Session duration in seconds.

*Extend session duration*
```hcl
iam_assume_role_duration = 7200  # 2 hours
```

Related: iam_role, iam_assume_role_session_name

## ATTRIBUTE: iam_assume_role_session_name

**IAM Assume Role Session Name Attribute**  |  Category: iam

Session name for the assumed IAM role. Useful for CloudTrail auditing.

**Syntax:**
```hcl
iam_assume_role_session_name = "<session_name>"
```

**Attributes:**
- `iam_assume_role_session_name` (string): Session name for IAM role assumption.

*Set session name for auditing*
```hcl
iam_assume_role_session_name = "terragrunt-${local.environment}-deploy"
```

Related: iam_role, iam_assume_role_duration

## ATTRIBUTE: iam_role

**IAM Role Attribute**  |  Category: iam

AWS IAM role ARN that Terragrunt will assume before running Terraform. Useful for cross-account deployments.

**Syntax:**
```hcl
iam_role = "<role_arn>"
```

**Attributes:**
- `iam_role` (string): IAM role ARN to assume.

*Assume role for deployment*
```hcl
iam_role = "arn:aws:iam::${local.account_id}:role/TerraformDeployRole"
```

**Broken on v1.1.1 — avoid that exact version.** Where static AWS credentials are supplied
*and* a role is configured (this attribute, `--iam-assume-role`, or `TG_IAM_ASSUME_ROLE`),
v1.1.1 made backend operations such as state-bucket bootstrapping perform a second role
assumption of their own. The run was already using the role session by then, so the role
tried to assume itself and AWS rejected it with `AccessDenied` unless the trust policy
happened to name the role itself. Fixed in v1.1.2, which reuses the session assumed at the
start of the run, as v1.1.0 and earlier did. Worth recognising because the error names a
trust-policy problem and invites you to go and edit the trust policy — the fix is the
upgrade. Does **not** affect `remote_state`'s `assume_role`: roles configured there are
backend-specific and are still assumed on top of the supplied credentials.

Related: iam_assume_role_duration, iam_assume_role_session_name

## ATTRIBUTE: iam_web_identity_token

**IAM Web Identity Token Attribute**  |  Category: iam

Path to a web identity token file for OIDC-based authentication. Used in CI/CD environments like GitHub Actions with AWS.

**Syntax:**
```hcl
iam_web_identity_token = "<path_to_token>"
```

**Attributes:**
- `iam_web_identity_token` (string): Path to OIDC web identity token file.

*Use OIDC token for AWS authentication*
```hcl
iam_web_identity_token = get_env("AWS_WEB_IDENTITY_TOKEN_FILE", "")
```

Related: iam_role

## BLOCK: include

**Include Block**  |  Category: modules

Includes configuration from another terragrunt.hcl file, enabling DRY (Don't Repeat Yourself) configuration patterns. Commonly used to include a root configuration with shared remote state and provider settings.

**Syntax:**
```hcl
include "<label>" { ... }
```

**Attributes:**
- `path` (string, required): Path to the terragrunt.hcl file to include. Use find_in_parent_folders("root.hcl") — bare find_in_parent_folders("root.hcl") targets a legacy root terragrunt.hcl; do not generate it.
- `expose` (boolean): When true, exposes the included config's locals and inputs for access via include.<label>.
- `merge_strategy` (string): how to merge the included configuration with the current one. Valid values: `no_merge` (do not merge), `shallow` (**the default**), `deep`.

*Include root configuration*
```hcl
include "root" {
  path = find_in_parent_folders("root.hcl")
}
```

*Include with exposed locals*
```hcl
include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

locals {
  # Access exposed variables from included config
  account_id = include.root.locals.account_id
}
```

Related: locals, terraform, remote_state

## ATTRIBUTE: inputs

**Inputs Block**  |  Category: core

Specifies the input variables to pass to the Terraform module. These values are automatically converted to TF_VAR_* environment variables when Terraform is executed.

**Syntax:**
```hcl
inputs = { ... }
```

**Attributes:**
- `<variable_name>` (any): Key-value pairs matching the Terraform module's input variables.

*Basic inputs from locals*
```hcl
inputs = {
  instance_type = local.instance_type
  environment   = local.environment
  tags          = local.tags
}
```

*Merge inputs from dependency outputs*
```hcl
inputs = merge(
  local.common_vars,
  {
    vpc_id     = dependency.vpc.outputs.vpc_id
    subnet_ids = dependency.vpc.outputs.private_subnet_ids
  }
)
```

Related: locals, dependency

## BLOCK: locals

**Locals Block**  |  Category: core

Defines local variables that can be referenced elsewhere in the Terragrunt configuration. Locals are evaluated lazily and can reference other locals, inputs, and built-in functions.

**Syntax:**
```hcl
locals { ... }
```

**Attributes:**
- `<variable_name>` (any): Any valid HCL expression. Variables defined here can be referenced as local.<variable_name>.

*Define reusable local variables*
```hcl
locals {
  environment = "production"
  region      = "us-east-1"

  # Computed values
  name_prefix = "${local.environment}-app"

  # Load from files
  account_vars = read_terragrunt_config(find_in_parent_folders("account.hcl"))
  account_id   = local.account_vars.locals.account_id
}
```

*Complex local with conditionals*
```hcl
locals {
  is_prod = local.environment == "production"

  instance_type = local.is_prod ? "m5.xlarge" : "t3.micro"

  tags = {
    Environment = local.environment
    ManagedBy   = "Terragrunt"
  }
}
```

Related: inputs, include

## ATTRIBUTE: prevent_destroy

**Prevent Destroy Attribute**  |  Category: execution

When set to true, Terragrunt will prevent any destroy operations on this module. This is a safety mechanism to protect critical infrastructure.

**Syntax:**
```hcl
prevent_destroy = <boolean>
```

**Attributes:**
- `prevent_destroy` (boolean): Whether to prevent destroy operations.

*Protect production database*
```hcl
prevent_destroy = local.environment == "production"
```

*Always prevent destroy*
```hcl
# Critical infrastructure - never destroy
prevent_destroy = true
```

Related: skip

## BLOCK: remote_state

**Remote State Block**  |  Category: core

Configures the OpenTofu/Terraform remote state backend. For the backends Terragrunt
**natively manages — `s3` and `gcs` — it auto-provisions the state resources** (S3
bucket + optional lock table; GCS bucket) if they don't exist. For **all other backends,
including `azurerm`, `remote_state` behaves like `generate`**: it writes the backend
config but does **not** create any cloud resources — the storage account/container must
already exist. (Azure auto-management is gated behind the no-op `azure-backend`
experiment.) See references/azure-backend.md.

**Syntax:**
```hcl
remote_state { ... }
```

**Attributes:**
- `backend` (string, required): The backend type — one of the backends OpenTofu/Terraform supports (`s3`, `gcs`, `azurerm`, ...).
- `config` (map, required): An arbitrary map used to fill in the backend configuration in OpenTofu/Terraform. For `azurerm`, every key is a pure pass-through to the native backend (see references/azure-backend.md for the key list).
- `generate` (object): Generate a backend file. Keys: `path` and `if_exists` (`overwrite`, `overwrite_terragrunt`, `skip`, `error`).
- `disable_init` (boolean): When `true`, skip Terragrunt's automatic creation/management of remote state resources (S3 buckets, lock tables, GCS buckets) while still letting OpenTofu/Terraform initialize an already-provisioned backend. (No effect for `azurerm`, which is never auto-created.)
- `disable_dependency_optimization` (boolean): Disable the optimized dependency-output fetching for modules using this block.
- `encryption` (map): Configures OpenTofu state/plan encryption; transformed into an `encryption` block. Cloud-agnostic (OpenTofu only).

*S3 backend with DynamoDB locking*
```hcl
remote_state {
  backend = "s3"
  config = {
    bucket         = "my-terraform-state"
    key            = "${path_relative_to_include()}/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-locks"
  }
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
}
```

*GCS backend*
```hcl
remote_state {
  backend = "gcs"
  config = {
    bucket   = "my-terraform-state"
    prefix   = "${path_relative_to_include()}"
    project  = "my-gcp-project"
    location = "us"
  }
}
```

*Azure (azurerm) backend — Entra ID auth, pure pass-through (storage must pre-exist)*
```hcl
remote_state {
  backend = "azurerm"
  config = {
    storage_account_name = "myterragruntstate"
    container_name       = "tfstate"
    key                  = "${path_relative_to_include()}/terraform.tfstate"
    resource_group_name  = "terraform-rg"
    subscription_id      = "00000000-0000-0000-0000-000000000000"
    use_azuread_auth     = true # Microsoft-recommended; avoids storage shared keys
  }
}
```
The keys above are passed straight to the native `azurerm` backend; Terragrunt does not
create the storage account/container. For the full key list, auth methods, and gotchas
(shared-key-disabled storage, RBAC roles, provider v4 `subscription_id`), see
references/azure-backend.md.

Related: terraform, generate

## BLOCK: catalog

**Catalog Block**  |  Category: core

Where Terragrunt looks for reusable patterns — OpenTofu/Terraform modules and Boilerplate
templates — for the `catalog` and `scaffold` commands, plus scaffolding behaviour.

**Syntax:**
```hcl
catalog {
  urls = [
    "/Users/acme/modules",
    "github.com/acme/infrastructure-modules",
  ]
  default_template = "/Users/acme/templates/default"
}
```

**Attributes:**
- `urls` (list, **required**): URLs pointing to module catalogs. Local file paths or remote
  URLs. Relative paths resolve against the configuration file.
- `default_template` (string, optional): a default Boilerplate template for scaffolding modules
  that do not carry their own `.boilerplate` directory.
- `no_shell` (boolean, optional, default `false`): disable shell command execution in
  Boilerplate templates during scaffolding. Overridable with `--no-shell`.
- `no_hooks` (boolean, optional, default `false`): disable hook execution in Boilerplate
  templates during scaffolding. Overridable with `--no-hooks`.

Scaffolding is performed by [boilerplate](https://github.com/gruntwork-io/boilerplate); see
`## COMMAND: scaffold` in `cli-reference.md` for the template resolution order and the
`boilerplate.yml` schema.

Related: terraform

## BLOCK: engine

**Engine Block**  |  Category: experimental

Experimental Terragrunt engine configuration. The blocks reference documents it as a stub and
points at <https://docs.terragrunt.com/features/units/engine/>; nothing further is stated there,
so nothing further is asserted here. Fetch that page before advising on it.

Related: terraform_binary

## BLOCK: feature

**Feature Block**  |  Category: execution

Feature flags in HCL, scoped to one Terragrunt unit. **Every flag must declare a default.**
Overridable at run time with `--feature` or `TG_FEATURE`.

**Syntax:**
```hcl
feature "string_flag" {
  default = "test"
}

feature "run_hook" {
  default = false
}

terraform {
  before_hook "feature_flag" {
    commands = ["apply", "plan", "destroy"]
    execute  = feature.run_hook.value ? ["sh", "-c", "feature_flag_script.sh"] : ["sh", "-c", "exit", "0"]
  }
}

inputs = {
  string_feature_flag = feature.string_flag.value
}
```

Read a flag as `feature.<name>.value`. This is the producer for the `if` condition on
`## BLOCK: exclude` — a unit is commonly excluded on a feature flag rather than on a hardcoded
condition.

Related: exclude, terraform, inputs

## BLOCK: errors

**Errors Block**  |  Category: execution

Retry and ignore policies for failures in the wrapped OpenTofu/Terraform command. **This is
the 1.x replacement for the pre-1.0 top-level `retryable_errors`, `retry_max_attempts` and
`retry_sleep_interval_sec` attributes**, which no longer exist as top-level attributes and
must not be emitted as such.

Both nested blocks take a **label**.

**Syntax:**
```hcl
errors {
  retry "transient_errors" {
    retryable_errors   = [".*Error: transient network issue.*"]
    max_attempts       = 3
    sleep_interval_sec = 5
  }
  ignore "known_safe_errors" {
    ignorable_errors = [
      ".*Error: safe warning.*",
      "!.*Error: do not ignore.*",
    ]
    message = "Ignoring safe warning errors"
    signals = {
      alert_team = false
    }
  }
}
```

**`retry "<label>"` attributes:**
- `retryable_errors` (list of strings, required): regex patterns matching errors eligible for retry.
- `max_attempts` (number, required): maximum retry attempts.
- `sleep_interval_sec` (number, required): seconds to wait between retries.

**`ignore "<label>"` attributes:**
- `ignorable_errors` (list of strings, required): regex patterns for errors to ignore. A `!`
  prefix negates — that pattern will NOT be ignored even if an earlier pattern matches it.
- `message` (string, optional): warning shown when an error is ignored.
- `signals` (map, optional): key/value pairs for signalling an external system.

> **`retryable_errors` is banned at the top level and correct HERE.** Same identifier, opposite
> verdict depending on where it sits. Inside `errors { retry {} }` it is the documented 1.x
> attribute; on its own at the top of a `terragrunt.hcl` it is the pre-1.0 form. A grep alone
> cannot tell them apart — check the enclosing block.

Verified against <https://docs.terragrunt.com/reference/hcl/blocks/> on 2026-08-19. The docs do
not state which release introduced this block; it is 1.x and the attributes it replaced were
pre-1.0.

Related: exclude, prevent_destroy

## BLOCK: exclude

**Exclude Block**  |  Category: execution

Conditionally leave a unit out of a run. **This is the 1.x replacement for the pre-1.0 `skip`
attribute**, which no longer exists and must not be emitted.

**Syntax:**
```hcl
exclude {
  if                   = feature.feature_name.value
  actions              = ["plan", "apply"]
  exclude_dependencies = false
}
```

**Attributes** (all optional):
- `if` (boolean): the condition deciding whether the exclusion applies.
- `actions` (list of strings): which actions to exclude when the condition holds. Documented
  values: `"plan"`, `"apply"`, `"all"`, `"all_except_output"`.
- `exclude_dependencies` (boolean, default `false`): whether the unit's dependencies are
  excluded too.
- `no_run` (boolean): prevents execution for **single-unit** commands matching `actions`.

Exclusion applies when the `if` condition is true **and** the current action appears in
`actions`.

> **`no_run` is ignored by `run --all`.** It applies only to single-unit commands such as
> `terragrunt run plan`. If you are trying to keep a unit out of a whole-tree run, `no_run` is
> not the attribute — use `if` and `actions`.

*Keep a production-only unit out of a dev run*
```hcl
exclude {
  if      = local.environment == "dev"
  actions = ["all"]
}
```

Verified against <https://docs.terragrunt.com/reference/hcl/blocks/> on 2026-08-19. The docs do
not state which release introduced this block, and they do not themselves describe it as the
successor to `skip`; that mapping comes from this skill's post-1.0 policy.

Related: errors, feature, prevent_destroy

## BLOCK: terraform

**Terraform Block**  |  Category: core

Specifies the Terraform source code to use and allows configuration of how Terragrunt interacts with Terraform. This is the primary block for defining what Terraform module to deploy.

**Syntax:**
```hcl
terraform { ... }
```

**Attributes:**
- `source` (string, required): where to fetch the module from — local path, Git URL, S3, GCS, an OCI image reference, or a `tfr://` registry address. **A bare `tfr:///` does not resolve to a fixed registry — see the subsection below before using one.**
- `version` (string): **Experiment `version-attribute`, v1.1.1+.** Resolves a `tfr://` registry module by version constraint instead of pinning an exact version in the source URL. Not available without the experiment flag — see below.
- `include_in_copy` (list): List of glob patterns for additional files to copy to the Terraform working directory. **v1.1.2 note:** for a *local* `source`, Terragrunt decides whether its cached copy is stale by hashing the source directory. Before v1.1.2 that hash covered every file in the directory — hidden files and `exclude_from_copy` matches included — so creating or touching a file that is never copied (an editor swap file, a scratch note) forced a needless re-copy and auto-init on the next run. The hash now covers only the files a copy would actually deliver, honouring the default hidden-file rule alongside `include_in_copy` and `exclude_from_copy`. **v1.1.3 note:** with the `fast-copy` strict control enabled, a hidden directory copied because `include_in_copy` matched something inside it took the permissions of the first file generated within it rather than its own source permissions. Such directories now keep their source permissions, matching the copy performed with the control disabled.
- `extra_arguments` (block): Nested block to pass additional CLI arguments to specific Terraform commands.
- `exclude_from_copy` (list): glob patterns always skipped when copying the directory
  containing `terragrunt.hcl` into the working directory. **Not mutually exclusive with
  `include_in_copy`** — a file matching both is NOT included, so if you need it, make sure the
  `include_in_copy` patterns do not also match an `exclude_from_copy` pattern.
- `copy_terraform_lock_file` (boolean, default `true`): disable copying the generated or
  existing `.terraform.lock.hcl` from the temp folder into the working directory. Use when you
  do not want the provider lock file checked into the source repo from the working directory.
- `mutable` (boolean, default `false`): when `true`, content fetched into `.terragrunt-cache`
  through the CAS is **copied** from the store and the working tree is editable. The default
  materialises files **read-only, so an accidental edit cannot reach back into the shared CAS
  store**. No effect when CAS is not used to fetch the source — the standard download path
  already produces an independent writable copy. See the three-way warning below.
- `update_source_with_cas` (boolean): rewrite a **relative, literal** `source` to a `cas::`
  reference. Two hard constraints, both of which fail at generation time rather than at plan:
  the `source` must be a literal string (interpolation, function calls and references such as
  `local.foo` all cause stack generation to fail), and `--no-cas` must NOT be set or Terragrunt
  errors out. Valid on `unit` in a `terragrunt.stack.hcl` as well — see `## BLOCK: unit`.
- `before_hook` (block): Nested block to execute commands before Terraform runs.
- `after_hook` (block): Nested block to execute commands after Terraform runs.
- `error_hook` (block): Nested block to execute commands when Terraform encounters an error.

*Basic Terraform source from Git*
```hcl
terraform {
  source = "git::https://github.com/gruntwork-io/terragrunt.git//modules/vpc?ref=v0.1.0"
}
```

*Local module with extra arguments*
```hcl
terraform {
  source = "../modules/vpc"

  extra_arguments "common_vars" {
    commands = ["apply", "plan", "import", "push", "refresh"]
    arguments = ["-var-file=${get_terragrunt_dir()}/common.tfvars"]
  }
}
```

**Source schemes gated behind experiments (v1.1.1+).** Both are opt-in and will fail on a repo that
has not enabled them, so confirm the pinned Terragrunt version and the enabled experiments before
emitting either. Enable with `--experiment <name>` or `TG_EXPERIMENT=<name>`.

*`oci` experiment — module source from an OCI Distribution registry*
```hcl
terraform {
  source = "oci://ghcr.io/acme/terraform-modules/vpc?tag=1.0.0"
}
```

### The `tfr:///` default registry depends on which engine Terragrunt is driving

`tfr://` accepts a shorthand with the host omitted — three slashes:

```hcl
source = "tfr:///terraform-aws-modules/vpc/aws?version=5.8.1"
```

**That shorthand is not portable between OpenTofu and Terraform.** From the Terragrunt docs:

> "The `tfr` protocol supports a shorthand notation where the `REGISTRY_HOST` can be omitted to
> default to the public registry. The default registry depends on the wrapped executable: for
> Terraform, it is `registry.terraform.io`, and for OpenTofu, it is `registry.opentofu.org`."

So the same config pulls from a different registry depending on what Terragrunt is wrapping.
Set it explicitly when it matters:

```hcl
source = "tfr://registry.terraform.io/terraform-aws-modules/vpc/aws?version=5.8.1"
```

or override the default for the whole run with the environment variable
**`TG_TF_DEFAULT_REGISTRY_HOST`**.

**Why this bites: the two registries are not the same set of modules.** The OpenTofu registry
is **not a mirror**. It is populated by GitHub search and by polling releases and tags, and a
repository has to be onboarded through an issue submission before any of its versions appear.
So a module — or a specific version of one — can exist on `registry.terraform.io` and not yet
on `registry.opentofu.org`. There is no published sync interval or SLA.

Both registries expose the same unauthenticated endpoint, so checking costs nothing:

```bash
curl -s https://registry.terraform.io/v1/modules/terraform-aws-modules/vpc/aws/versions
curl -s https://registry.opentofu.org/v1/modules/terraform-aws-modules/vpc/aws/versions
```

For anything beyond "does this version exist" — required inputs, outputs, what changed between
versions — use the `terraform-registry` skill rather than reading registry JSON by hand.

Verified against docs.terragrunt.com and both registry APIs on 2026-08-19. Not determined: the
exact mechanism by which Terragrunt decides which executable it is wrapping for this purpose —
the docs say only "the wrapped executable" and do not name `terraform_binary` or an `engine`
block in that context. If the distinction is load-bearing for you, set the host explicitly
rather than relying on detection.

*`version-attribute` experiment — resolve a `tfr://` registry module by constraint*
```hcl
terraform {
  source  = "tfr://registry.opentofu.org/terraform-aws-modules/vpc/aws"
  version = "~> 3.3"
}
```

Prefer the `version` attribute over embedding an exact version in a `tfr://` URL *only* where the
experiment is enabled; otherwise keep pinning in the source string, which works on every 1.x.

**`source` cannot reference `dependency` outputs.** A module's source must resolve before the
dependency graph runs, so `source = "${dependency.foo.outputs.bar}"` is not a late-binding
expression — it is a cycle Terragrunt cannot satisfy. v1.1.1 replaced the previous confusing
failure with an explicit error saying module sources must resolve before dependencies run. If a
source genuinely varies per environment, drive it from `locals`/`inputs` or an `include`, never
from a dependency.

Related: remote_state, include, dependency

## ATTRIBUTE: terraform_binary

**Terraform Binary Attribute**  |  Category: terraform

Path to a custom Terraform binary. Useful when you need to use a specific version or a wrapper like Terraform Enterprise CLI.

**Syntax:**
```hcl
terraform_binary = "<path>"
```

**Attributes:**
- `terraform_binary` (string): Path to Terraform binary.

*Use specific Terraform version*
```hcl
terraform_binary = "/usr/local/bin/terraform-1.5.7"
```

*Use tfenv-managed version*
```hcl
terraform_binary = "~/.tfenv/bin/terraform"
```

Related: terraform_version_constraint

## ATTRIBUTE: terragrunt_version_constraint

**Terragrunt Version Constraint Attribute**  |  Category: core

Which versions of the **Terragrunt CLI** may be used with this configuration. If the running
version does not satisfy the constraint, Terragrunt errors and exits without taking any further
action.

**Syntax:**
```hcl
terragrunt_version_constraint = ">= 0.23"
```

> **Not the same attribute as `terraform_version_constraint`**, which constrains the wrapped
> OpenTofu/Terraform binary. Both exist, the names differ by one word, and they gate different
> things.

Related: terraform_version_constraint, terraform_binary

## ATTRIBUTE: terraform_version_constraint

**Terraform Version Constraint Attribute**  |  Category: terraform

Specifies the required Terraform version. Terragrunt will check this before running and fail if the version doesn't match.

**Syntax:**
```hcl
terraform_version_constraint = "<constraint>"
```

**Attributes:**
- `terraform_version_constraint` (string): Terraform version constraint (uses same syntax as Terraform).

*Require minimum version*
```hcl
terraform_version_constraint = ">= 1.0"
```

*Pin to specific minor version*
```hcl
terraform_version_constraint = "~> 1.5.0"
```

Related: terraform_binary

## BLOCK: unit

**Unit Block (terragrunt.stack.hcl)**  |  Category: stacks

Declares one unit to materialize when `terragrunt stack generate` expands a
`terragrunt.stack.hcl` file. Each `unit` becomes a directory under `.terragrunt-stack/`
containing a generated `terragrunt.hcl` (plus a `terragrunt.values.hcl` if `values` is
set). Lives **only** in `terragrunt.stack.hcl`, not in a unit's own `terragrunt.hcl`.

**Syntax:**
```hcl
unit "<name>" { ... }
```

**Attributes:**
- `<name>` (label, required): unique identifier for the unit within the stack; also its referenceable name. Each unit must have a unique name **and** `path`.
- `source` (string, required): where to fetch the unit's config from — same syntax as the `terraform` block `source`: local path, `git::…?ref=…`, `tfr://` registry, or an OCI image reference. Overridable with `--source-map`.
- `path` (string, required): relative path where the unit is deployed inside `.terragrunt-stack/`.
- `values` (map, optional): values passed to the unit; written to a generated `terragrunt.values.hcl` next to the unit's `terragrunt.hcl` and read inside it as `values.<key>`.
- `no_dot_terragrunt_stack` (boolean, optional): generate the unit in the same directory as `terragrunt.stack.hcl` instead of under `.terragrunt-stack/`. Intended for soft adoption / state migration (keeps `path_relative_to_include()` stable), not the recommended end state.
- `no_validation` (boolean, optional): skip Terragrunt's validation of this unit's configuration.
- **v1.1.0+ only** (GA in v1.1.0, 2026-07-01 — do NOT emit for repos pinned to ≤1.0.x): `autoinclude` (block; generates a `terragrunt.autoinclude.hcl` merged into the unit, e.g. to declare a `dependency` using `unit.<name>.path` — see `## BLOCK: autoinclude`), `update_source_with_cas` (boolean, default `false`; on `stack generate`, rewrites a **relative, literal** `source` within the same repo to a `cas::sha1:…` reference so the generated tree is self-contained — set by catalog authors, not consumers; errors if `--no-cas` is set), `mutable` (boolean, default `false`; `false` hard-links CAS content read-only, `true` copies it so the working tree is editable). These graduated from the `stack-dependencies` / `cas` experiments. `dependency` targeting a stack directory is supported **via an `autoinclude` block** (units may depend on stacks; stacks cannot depend on stacks or units). `include` blocks in stack files: the v1.1.0 changelog says they now work, but the Stacks "Limitations" doc still lists them unsupported — docs lag, verify against the pinned version first.

*Unit pulling a catalog module, with values*
```hcl
unit "rds" {
  source = "${local.infra_root}/catalog/units/rds"
  path   = "rds"
  values = {
    instance_class = "db.t3.medium"
    environment    = "prod"
  }
}
```
Inside `catalog/units/rds/terragrunt.hcl` those are read as `values.instance_class`, `values.environment`.

Related: stack, terraform

## BLOCK: stack

**Stack Block (terragrunt.stack.hcl)**  |  Category: stacks

Declares a **nested stack** inside a `terragrunt.stack.hcl`. Identical attributes and
semantics to `unit`, except the `source` must point at a directory containing its own
`terragrunt.stack.hcl`; generation produces a nested `terragrunt.stack.hcl` under the given
`path` (which is then itself expanded). Use it to compose stacks of stacks.

**Syntax:**
```hcl
stack "<name>" { ... }
```

**Attributes:** same as `unit` — `<name>` (label, required), `source` (required), `path`
(required), `values`, `no_dot_terragrunt_stack`, `no_validation`, and the same v1.1.0+
additions (`autoinclude` with `stack.<name>.path` refs, `update_source_with_cas`, `mutable`).
- **v1.1.3, `block-iteration` experiment, RESERVED ONLY:** a nested `expansion` block on
  `dependency`, `unit` and `stack` is the declared gate for iterating that block over a
  `count` or `for_each`, alongside an `enabled` attribute on `unit` and `stack`. In v1.1.3
  **enabling the experiment has no behavioural effect** — the flag is reserved. What did
  change is the failure mode: writing an `expansion` block without the experiment now errors
  naming the flag, where it was previously discarded in silence. Do not emit `expansion` or
  `enabled` yet. Track https://github.com/gruntwork-io/terragrunt/issues/4504.

*Nested stack instantiated per region*
```hcl
stack "networking" {
  source = "${local.infra_root}/catalog/stacks/networking"
  path   = "networking"
  values = { region = "eastus" }
}
```

Related: unit, terraform

## BLOCK: autoinclude

**Autoinclude Block (terragrunt.stack.hcl)**  |  Category: stacks  |  **v1.1.0+ only**

Nested inside a `unit` or `stack` block. On `terragrunt stack generate`, its body is
written to a `terragrunt.autoinclude.hcl` file next to the generated `terragrunt.hcl` (or
`terragrunt.stack.hcl`) and **merged into that unit/stack when it is parsed** — the catalog
source itself is never modified. This is how a stack wires its own units together and patches
catalog components with config they don't ship. GA in v1.1.0 (was the `stack-dependencies`
experiment). Requires **v1.1.0+** — do NOT emit for repos pinned to ≤1.0.x.

**Syntax:**
```hcl
unit "app" {
  source = "../catalog/units/app"
  path   = "app"

  autoinclude {
    dependency "vpc" {
      config_path  = unit.vpc.path      # resolves to the generated dir of the "vpc" unit
      mock_outputs = { vpc_id = "vpc-mock" }
    }

    inputs = {
      vpc_id = dependency.vpc.outputs.vpc_id
    }
  }
}
```

- **Body:** anything valid in a unit configuration — `dependency`, `inputs`, `errors`
  (e.g. `retry`), etc. It is merged, so it adds to / overrides the catalog unit's config.
- **`unit.<name>.path` / `stack.<name>.path`:** resolve to the generated path of a sibling
  block, so dependency wiring never hardcodes `.terragrunt-stack/…` paths.
- **Dependency on a stack:** a `dependency` declared in an `autoinclude` block *may* set
  `config_path` to a stack directory and read its aggregated outputs — this is the supported
  way to depend on a stack. A plain top-level `dependency` block cannot target a stack dir.
  Relationship is one-way: units depend on stacks; stacks cannot depend on stacks or units.
- The generated `terragrunt.autoinclude.hcl` is stack output — gitignore `.terragrunt-stack/`.

Docs: https://docs.terragrunt.com/features/stacks/explicit/ (Declaring Dependencies Between
Units) · https://docs.terragrunt.com/reference/hcl/blocks#autoinclude

Related: unit, stack, dependency, include
