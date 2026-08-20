# Terragrunt Best Practices & Decision Guidance

> Source: curated data harvested from omattsson/terragrunt-mcp-server, restructured for grep-based lookup.
> Content spot-checked against docs.terragrunt.com at **v1.1.0** (2026-07-01); reviewed against the **v1.1.1** release notes (2026-07-14) on 2026-07-29 with no changes required — v1.1.1 was bug-fix only, and its two new experiments touch the `terraform` block (see hcl-blocks.md). Flag and avoid any pre-1.0 idioms.

Sections: PRACTICE (by category), COMPARISON (block A vs B), DECISION (pattern guidance).

## PRACTICE: Use run --all with --parallelism for efficient CI/CD pipelines

**Category:** ci_cd  |  **Priority:** recommended  |  **Level:** intermediate

**Why:** `run --all` walks the units in dependency order. Parallelism speeds that up while
staying inside provider API rate limits.

**Mind the `--` separator.** The documented form is `terragrunt run [flags] -- [tofu command]`.
Terragrunt's own flags go *before* the separator; everything after it is passed through to
OpenTofu/Terraform. Putting `--parallelism` after the subcommand is a common and avoidable
mistake.

```bash
# Apply every unit in dependency order, five at a time
terragrunt run --all --parallelism 5 -- apply

# Plan every unit, ten at a time
terragrunt run --all --parallelism 10 -- plan
```

`run --all` with `apply` or `destroy` **silently adds `-auto-approve`**, because a shared stdin
makes per-unit approval impossible. That is what you want in CI; know that it is happening, and
use `--no-auto-approve` if you do not.

**Antipatterns:**
- Applying units one at a time in a shell loop
- Unlimited parallelism (provider API rate limiting)
- Omitting `--non-interactive` in CI
- Putting a Terragrunt flag after the OpenTofu subcommand instead of before the `--`

**Tradeoffs:** higher parallelism is faster but makes more API calls, and a failed `run --all`
apply is harder to unpick than a single unit.

## PRACTICE: Implement plan/apply separation with artifact storage in pipelines

**Category:** ci_cd  |  **Priority:** recommended  |  **Level:** intermediate

**Why:** Applying a saved plan guarantees that what was reviewed is what gets applied. It also
gives the review workflow something concrete to look at and leaves an audit trail.

**Use `--out-dir`, not `-out=`.** A single `-out=tfplan` cannot work across a stack, because the
path is relative to each unit — every unit would write to the same name in its own directory and
nothing would gather them. `--out-dir` writes one plan per unit, mirroring the stack's directory
structure under the directory you name.

```yaml
# GitLab CI
plan:
  stage: plan
  script:
    - cd live/${ENVIRONMENT}
    - terragrunt run --all --out-dir "$CI_PROJECT_DIR/.tfplan" -- plan
  artifacts:
    paths:
      - .tfplan/
    expire_in: 1 day

apply:
  stage: apply
  needs: [plan]
  when: manual
  script:
    - cd live/${ENVIRONMENT}
    - terragrunt run --all --out-dir "$CI_PROJECT_DIR/.tfplan" -- apply
```

Two rules the docs are explicit about:

- **Apply fails if any unit has no saved plan.** "Performing a `run --all --out-dir <dir> --
  apply` requires that a plan already exists for each unit in the stack."
- **A `--filter` must match between the plan and the apply.** Plan a narrower set than you
  apply and the apply fails on the units you never planned.

Add `--json-out-dir` alongside `--out-dir` if you want machine-readable plans for a policy
check or a PR comment.

See `references/cicd.md` for the full pipeline, including OIDC to AWS, GCP and Azure.

**Antipatterns:**
- Running plan and apply in the same job
- Not storing plan artifacts
- Applying without the saved plan file

**Tradeoffs:** More complex pipeline configuration; Plan files can become stale if not applied promptly

## PRACTICE: Make the pipeline the only path to production

**Category:** ci_cd  |  **Priority:** critical  |  **Level:** intermediate

**Why:** Manual `apply` to production from a laptop has no audit trail, depends on one person's
memory, and bypasses review. The CI/CD pipeline should be the *exclusive* mechanism for
deploying to prod; humans have read-only access outside it. The git history of the live repo
then becomes the audit trail of who changed what and why. This also enforces the
plan → review → apply gate.

**When an LLM/agent drives Terragrunt** this rule is non-negotiable: generate/modify the HCL,
run `plan`, surface it for review, and let the pipeline apply — **never** `apply` (or
`apply -auto-approve` outside the controlled `run --all` stack flow) directly against prod.
The agent-side discipline (generate IaC not direct cloud changes; query state before acting;
plan→review→apply; never apply/push directly) lives in the **dev-fleet** skill — follow it.

**Antipatterns:**
- Humans with standing write/apply access to production
- `apply` run from a workstation instead of the pipeline
- An agent applying generated changes directly instead of opening a reviewable plan

**Tradeoffs:** Requires a real pipeline + access controls; emergency break-glass needs a
deliberate, audited exception path.

## PRACTICE: Separate live config from a versioned module/unit catalog

**Category:** structure  |  **Priority:** recommended  |  **Level:** intermediate

**Why:** Keep environment-specific configuration (`infrastructure-live`) separate from the
reusable, security-defaulted unit/module definitions it consumes (`infrastructure-catalog`).
The live repo references catalog units by **pinned** `source = "git::…//units/x?ref=vX.Y.Z"`,
so a catalog change is adopted deliberately (bump the `ref`), not implicitly. Promotion across
environments is then "same stack, same unit sources, only `values` differ" — a small,
reviewable diff. (See `references/architecture-patterns.md` `## PATTERN: explicit stacks`.)

**Antipatterns:**
- Editing shared module code and having it hit every environment at once
- Catalog references pinned to `main`/`latest` (see the module-versioning practice)
- Duplicating whole environment folders instead of varying `values`

**Tradeoffs:** Two repos (or a clear in-repo split) to manage; a version bump step to adopt
catalog changes — which is the point.

## PRACTICE: Audit machine-generated Terragrunt before trusting it

**Category:** review  |  **Priority:** recommended  |  **Level:** intermediate

**Why:** AI/codegen emits plausible-but-wrong Terragrunt fast. As the cost of *generating*
falls, the cost of *verifying* must rise — generated HCL is not trustworthy until proven.

- **Treat the generator's input model/spec as the contract:** confirm the generated config
  reflects it — no dropped fields, no invented inputs (a conformance check, not a vibe).
- **Run a no-op proof:** `terragrunt run --all plan` (or per-unit `plan`) and require **no
  unintended changes** — no create/destroy/replace, no state-key churn — before applying. A
  clean plan is the audit gate. (Same parity check used when migrating to stacks.)
- **Validate structure cheaply first:** `terragrunt hcl validate` / `hcl fmt --check`, then
  the REVIEW checklist (1.0-policy violations, include-graph integrity, dependency/mock
  hygiene).
- **Don't let "the tool generated it" lower the bar** — review the diff like any change.

**Antipatterns:**
- Applying generated Terragrunt without a reviewed plan
- Trusting generated inputs match the source model without a conformance check
- Treating a green `plan` exit as "no changes" without reading it (use `-detailed-exitcode`)

## PRACTICE: Always provide mock_outputs for dependencies to enable isolated planning

**Category:** dependencies  |  **Priority:** critical  |  **Level:** intermediate

**Why:** Mock outputs allow terragrunt plan to succeed even when dependent modules haven't been applied yet. This is essential for CI/CD pipelines and developing new modules.

```hcl
dependency "vpc" {
  config_path = "../vpc"

  mock_outputs = {
    vpc_id            = "vpc-00000000000000000"
    vpc_cidr          = "10.0.0.0/16"
    private_subnet_ids = ["subnet-00000000000000001", "subnet-00000000000000002"]
    public_subnet_ids  = ["subnet-00000000000000003", "subnet-00000000000000004"]
  }

  # Only use mocks for validate and plan
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}
```

**Antipatterns:**
- No mock outputs, breaking CI/CD plans
- Mock outputs that don't match real output structure
- Allowing mock outputs during apply

**Tradeoffs:** Must keep mock outputs in sync with module outputs; Mocks may not catch type/structure mismatches

## PRACTICE: Minimize dependency depth to avoid long apply chains

**Category:** dependencies  |  **Priority:** recommended  |  **Level:** advanced

**Why:** Deep dependency chains increase apply time, make troubleshooting harder, and create more points of failure. Design for shallow, parallel-friendly dependency graphs.

```hcl
# Good: Shallow dependencies (max 2-3 levels)
vpc (no deps)
├── security-groups (depends on vpc)
├── eks-cluster (depends on vpc, security-groups)
└── rds (depends on vpc, security-groups)

# Avoid: Deep chains
vpc -> subnet -> route-table -> nat-gateway -> security-group -> eks -> nodegroup
```

**Antipatterns:**
- Linear chains of 5+ dependencies
- Every module depending on a "base" module
- Circular dependencies (Terragrunt will error)

**Tradeoffs:** May need to combine some resources to reduce deps; Flatter structures may have more parallel applies

## PRACTICE: Use get_env() for sensitive values and credentials from environment variables

**Category:** environment_config  |  **Priority:** critical  |  **Level:** beginner

**Why:** Environment variables keep secrets out of version control, integrate well with CI/CD systems and secret managers, and follow the twelve-factor app methodology.

```hcl
# Using get_env for sensitive values
locals {
  db_password = get_env("DB_PASSWORD", "")
  api_key     = get_env("API_KEY")  # Required, no default
}

inputs = {
  database_password = local.db_password
  api_key           = local.api_key
}
```

**Antipatterns:**
- Hardcoding passwords or API keys in terragrunt.hcl
- Committing .env files with real credentials
- Using default values for sensitive data in production

**Tradeoffs:** Requires environment variable setup in CI/CD; Local development needs .env file or exports

## PRACTICE: Define environment-specific variables in dedicated configuration files per environment level

**Category:** environment_config  |  **Priority:** critical  |  **Level:** beginner

**Why:** Centralizing environment variables in env.hcl, account.hcl, or region.hcl files makes it easy to understand what differs between environments and reduces duplication.

```hcl
# live/dev/env.hcl
locals {
  environment = "dev"

  # Environment-specific settings
  instance_type    = "t3.small"
  min_size         = 1
  max_size         = 3
  enable_deletion_protection = false
}
```

**Antipatterns:**
- Scattering environment-specific values across many files
- Using conditionals based on path to determine environment
- Not having a clear source of truth for environment settings

**Tradeoffs:** Requires consistent file naming across environments; Changes to structure affect all child modules

## PRACTICE: Use dependency blocks with mock_outputs for cross-module data sharing

**Category:** environment_config  |  **Priority:** critical  |  **Level:** intermediate

**Why:** Dependencies allow modules to reference outputs from other modules. mock_outputs enable planning and applying modules in isolation during development.

```hcl
dependency "vpc" {
  config_path = "../vpc"

  # Mock outputs for plan/apply when VPC doesn't exist yet
  mock_outputs = {
    vpc_id     = "vpc-mock-12345"
    subnet_ids = ["subnet-mock-1", "subnet-mock-2"]
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
  mock_outputs_merge_strategy_with_state  = "shallow"
}

dependency "security_group" {
  config_path = "../security-group"

  mock_outputs = {
    security_group_id = "sg-mock-12345"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

inputs = {
  vpc_id            = dependency.vpc.outputs.vpc_id
  subnet_ids        = dependency.vpc.outputs.subnet_ids
  security_group_id = dependency.security_group.outputs.security_group_id
}
```

**Antipatterns:**
- Hardcoding resource IDs instead of using dependencies
- Not providing mock_outputs, breaking isolated plans
- Using data sources when a dependency would be cleaner

**Tradeoffs:** Creates implicit ordering requirements; Mock values may not reflect real resource behavior

## PRACTICE: Use feature flags for gradual rollouts and environment-specific features

**Category:** environment_config  |  **Priority:** optional  |  **Level:** advanced

**Why:** Feature flags allow enabling/disabling functionality per environment without code changes. Terragrunt feature blocks provide a clean pattern for this.

```hcl
# Define feature flags
feature "enable_monitoring" {
  default = false
}

feature "use_spot_instances" {
  default = false
}

locals {
  # Feature flags from environment
  monitoring_enabled = feature.enable_monitoring.value
  use_spot           = feature.use_spot_instances.value
}

inputs = {
  enable_cloudwatch_alarms = local.monitoring_enabled
  enable_datadog           = local.monitoring_enabled
  use_spot_instances       = local.use_spot
}
```

**Antipatterns:**
- Using complex conditionals based on environment name
- Hardcoding feature availability per environment in code
- Not having a centralized way to manage feature flags

**Tradeoffs:** Additional complexity for simple on/off decisions; Must track which features are enabled where

## PRACTICE: Use include with merge_strategy for flexible configuration inheritance

**Category:** environment_config  |  **Priority:** recommended  |  **Level:** intermediate

**Why:** The merge_strategy option controls how included configurations combine with local settings. Understanding and using this correctly enables DRY configurations while maintaining flexibility.

```hcl
# deep merge - recursively merges maps and lists
include "envcommon" {
  path           = "${dirname(find_in_parent_folders("root.hcl"))}/live/_envcommon/vpc.hcl"
  merge_strategy = "deep"
  expose         = true  # Access included locals via include.envcommon.locals
}

# Local inputs are deep merged with included inputs
inputs = {
  tags = {
    Team = "platform"  # Merged with tags from _envcommon
  }
}
```

**Antipatterns:**
- Not specifying merge_strategy and relying on defaults
- Using deep merge when you want to replace entire blocks
- Not using expose when you need to reference included locals

**Tradeoffs:** deep merge can produce unexpected results with complex nested structures; no_merge requires more explicit configuration

## PRACTICE: Use locals for computed values and keep inputs simple

**Category:** environment_config  |  **Priority:** recommended  |  **Level:** beginner

**Why:** The locals block is for computing values, transforming data, and assembling configuration. Inputs should receive final values, not contain complex logic.

```hcl
locals {
  # Load configuration files
  env_vars     = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  region_vars  = read_terragrunt_config(find_in_parent_folders("region.hcl"))
  account_vars = read_terragrunt_config(find_in_parent_folders("account.hcl"))

  # Extract commonly used values
  environment = local.env_vars.locals.environment
  region      = local.region_vars.locals.aws_region
  account_id  = local.account_vars.locals.account_id

  # Compute derived values
  name_prefix = "${local.environment}-${local.region}"

  # Standard tags
  common_tags = {
    Environment = local.environment
    Region      = local.region
    ManagedBy   = "terragrunt"
    Project     = "infrastructure"
  }
}

# Inputs are clean and simple
inputs = {
  name_prefix = local.name_prefix
  tags        = local.common_tags
  vpc_cidr    = local.env_vars.locals.vpc_cidr
}
```

**Antipatterns:**
- Putting complex expressions directly in inputs block
- Repeating the same read_terragrunt_config calls in multiple places
- Not extracting repeated values into named locals

**Tradeoffs:** More lines of code in locals block; Must scroll to find actual input values

## PRACTICE: Keep Terraform modules small, focused, and single-purpose

**Category:** module_organization  |  **Priority:** critical  |  **Level:** beginner

**Why:** Small modules are easier to understand, test, and reuse. They have fewer inputs, clearer interfaces, and can be composed together for complex deployments.

```hcl
# Good: Single-purpose modules
modules/
├── vpc/                    # Just VPC, subnets, route tables
├── eks-cluster/           # Just EKS control plane
├── eks-node-group/        # Just node groups
├── rds-instance/          # Just RDS, no networking
└── security-group/        # Just security group rules
```

**Antipatterns:**
- Creating "god modules" that deploy entire environments
- Modules with 50+ input variables
- Combining unrelated resources (e.g., VPC + database + application)

**Tradeoffs:** More modules to maintain; More dependency relationships to manage; May need wrapper modules for common patterns

## PRACTICE: Version your Terraform modules and pin versions in Terragrunt

**Category:** module_organization  |  **Priority:** critical  |  **Level:** beginner

**Why:** Version pinning ensures reproducible deployments, allows controlled upgrades, and prevents breaking changes from affecting production unexpectedly.

```hcl
# Pin to specific version tag
terraform {
  source = "git::git@github.com:myorg/modules.git//vpc?ref=v1.2.3"
}
```

**Antipatterns:**
- Using ref=main or ref=master for production
- Not versioning modules at all
- Different production instances using different versions unintentionally

**Tradeoffs:** Requires discipline to upgrade versions; May miss important bug fixes if not updated regularly

## PRACTICE: Document module interfaces with clear input/output descriptions

**Category:** module_organization  |  **Priority:** recommended  |  **Level:** beginner

**Why:** Good documentation in variable and output blocks makes modules self-documenting, helps consumers understand expected values, and enables better IDE/tooling support.

```hcl
# In Terraform module: variables.tf
variable "vpc_cidr" {
  type        = string
  description = "CIDR block for the VPC. Must be a valid IPv4 CIDR (e.g., 10.0.0.0/16)"

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr))
    error_message = "vpc_cidr must be a valid CIDR block."
  }
}

variable "enable_dns_hostnames" {
  type        = bool
  default     = true
  description = "Enable DNS hostnames in the VPC. Required for EKS and many AWS services."
}
```

**Antipatterns:**
- Variables without descriptions
- Outputs without descriptions
- Generic descriptions like "the value" or "input variable"

**Tradeoffs:** More time writing documentation; Descriptions can become outdated if not maintained

## PRACTICE: Use the Terragrunt cache to speed up repeated operations

**Category:** performance  |  **Priority:** recommended  |  **Level:** intermediate

**Why:** Terragrunt caches downloaded modules and providers. Preserving this cache between CI runs significantly speeds up operations.

```hcl
# GitHub Actions cache example
- name: Cache Terragrunt
  uses: actions/cache@v3
  with:
    path: |
      ~/.terragrunt-cache
      ~/.terraform.d/plugin-cache
    key: ${{ runner.os }}-terragrunt-${{ hashFiles('**/*.hcl') }}
```

**Antipatterns:**
- Downloading providers on every CI run
- Not caching Terragrunt module downloads
- Clearing caches unnecessarily

**Tradeoffs:** Cache management complexity; Stale caches can cause issues

## PRACTICE: Use run --all with appropriate parallelism based on provider rate limits

**Category:** performance  |  **Priority:** recommended  |  **Level:** advanced

**Why:** Too much parallelism can hit API rate limits; too little wastes time. Tune based on your cloud provider and module count.

```hcl
# AWS: Generally safe with 5-10 parallel operations
terragrunt run --all apply --parallelism 5

# For many small modules, can go higher
terragrunt run --all plan --parallelism 20

# For rate-limited APIs or large state files, go lower
terragrunt run --all apply --parallelism 2
```

**Antipatterns:**
- Unlimited parallelism causing rate limit errors
- Serial execution (parallelism=1) for independent modules
- Not adjusting parallelism for different operations

**Tradeoffs:** Higher parallelism = faster but riskier; May need to tune based on time of day/load

## PRACTICE: Separate live infrastructure from reusable modules using distinct directories

**Category:** project_structure  |  **Priority:** critical  |  **Level:** beginner

**Why:** Keeping live environment configurations separate from reusable module definitions provides clear separation of concerns, makes it easier to manage environment-specific settings, and enables module reuse across projects.

```hcl
# Recommended project structure
├── live/                    # Environment-specific configurations
│   ├── dev/
│   │   ├── us-east-1/
│   │   │   ├── vpc/
│   │   │   │   └── terragrunt.hcl
│   │   │   └── eks/
│   │   │       └── terragrunt.hcl
│   │   └── terragrunt.hcl   # Dev environment root
│   ├── staging/
│   └── prod/
├── modules/                 # Reusable Terraform modules
│   ├── vpc/
│   ├── eks/
│   └── rds/
└── terragrunt.hcl          # Root configuration
```

**Antipatterns:**
- Mixing environment configs and module code in the same directory
- Duplicating module code across environments instead of referencing shared modules
- Using a flat structure without environment/region organization

**Tradeoffs:** More directories to navigate but clearer organization; Requires understanding of include/dependency patterns

## PRACTICE: Use a root terragrunt.hcl for common configuration shared across all environments

**Category:** project_structure  |  **Priority:** critical  |  **Level:** beginner

**Why:** A root configuration file prevents duplication of common settings like remote state backend configuration, provider generation, and shared variables. Child configurations can include and override as needed.

```hcl
# Root terragrunt.hcl
remote_state {
  backend = "s3"
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
  config = {
    bucket         = "my-terraform-state"
    key            = "${path_relative_to_include()}/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-locks"
  }
}

generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
provider "aws" {
  region = "us-east-1"
}
EOF
}
```

**Antipatterns:**
- Copying remote_state configuration to every child module
- Not using include to reference parent configurations
- Hardcoding backend keys instead of using path_relative_to_include()

**Tradeoffs:** All environments share the same backend configuration pattern; Changes to root config affect all environments

## PRACTICE: Use _envcommon directory for configurations shared within an environment

**Category:** project_structure  |  **Priority:** recommended  |  **Level:** intermediate

**Why:** The _envcommon pattern allows you to define module configurations that are common across all deployments within an environment, reducing duplication while allowing per-deployment overrides.

```hcl
# Directory structure with _envcommon
├── live/
│   ├── _envcommon/
│   │   ├── vpc.hcl          # Common VPC config
│   │   └── eks.hcl          # Common EKS config
│   ├── dev/
│   │   ├── us-east-1/
│   │   │   └── vpc/
│   │   │       └── terragrunt.hcl  # Includes _envcommon/vpc.hcl
│   │   └── eu-west-1/
│   │       └── vpc/
│   │           └── terragrunt.hcl  # Includes _envcommon/vpc.hcl
```

**Antipatterns:**
- Duplicating module source and common inputs in every terragrunt.hcl
- Not leveraging merge_strategy for flexible overrides

**Tradeoffs:** Additional indirection can make debugging harder; Must understand merge_strategy options (deep, shallow, no_merge)

## PRACTICE: Organize directories by environment, then region/account, then unit

**Category:** project_structure  |  **Priority:** recommended  |  **Level:** beginner

**Why:** A consistent hierarchy of environment > region > unit makes it easy to understand what infrastructure exists where, enables targeted operations on specific environments or regions, and supports multi-region deployments.

```hcl
# Recommended hierarchy
live/
├── dev/
│   ├── account.hcl          # Dev AWS account ID
│   ├── us-east-1/
│   │   ├── region.hcl       # Region-specific settings
│   │   ├── vpc/
│   │   ├── eks/
│   │   └── rds/
│   └── us-west-2/
│       ├── region.hcl
│       └── vpc/
├── staging/
│   └── us-east-1/
└── prod/
    ├── us-east-1/
    └── eu-west-1/
```

**Antipatterns:**
- Flat structure mixing all environments in one directory
- Organizing by unit type first (all VPCs together) instead of by environment
- Inconsistent hierarchy across different parts of the codebase

**Tradeoffs:** Deeper directory nesting; More files to maintain (env.hcl, region.hcl per level)

## PRACTICE: Use consistent naming conventions for terragrunt.hcl files and directories

**Category:** project_structure  |  **Priority:** recommended  |  **Level:** beginner

**Why:** Consistent naming makes automation easier, improves discoverability, and helps team members navigate the codebase. Use lowercase with hyphens or underscores.

```hcl
# Good naming conventions
live/
├── dev/
│   └── us-east-1/
│       ├── vpc-main/           # Descriptive, lowercase, hyphens
│       ├── eks-cluster/
│       ├── rds-postgres/
│       └── lambda-api/
```

**Antipatterns:**
- Using generic names like "module1", "infra", "stuff"
- Mixing naming conventions (camelCase, PascalCase, snake_case)
- Names that don't indicate what the module deploys

**Tradeoffs:** Longer directory names vs clarity; May need to update automation scripts when renaming

## PRACTICE: Never commit sensitive values to version control

**Category:** security  |  **Priority:** critical  |  **Level:** beginner

**Why:** Credentials, passwords, and API keys in version control are a major security risk. They persist in git history even after deletion and can be easily exposed.

```hcl
# Use environment variables
locals {
  db_password = get_env("DB_PASSWORD")
}

# Use secret managers
data "aws_secretsmanager_secret_version" "db" {
  secret_id = "prod/database/password"
}
```

**Antipatterns:**
- Hardcoding passwords in terragrunt.hcl
- Committing .env files with real values
- Using default values for secrets

**Tradeoffs:** Requires external secret management setup; Local development needs secret access configured

## PRACTICE: Enable encryption for remote state storage

**Category:** security  |  **Priority:** critical  |  **Level:** beginner

**Why:** State files can contain sensitive data like passwords and private keys. Server-side encryption protects data at rest.

```hcl
# S3 backend with encryption
remote_state {
  backend = "s3"
  config = {
    bucket  = "terraform-state"
    key     = "${path_relative_to_include()}/terraform.tfstate"
    encrypt = true  # Server-side encryption

    # Optional: Use KMS key for additional control
    kms_key_id = "arn:aws:kms:us-east-1:123456789:key/12345678-1234-1234-1234-123456789"
  }
}
```

**Antipatterns:**
- Unencrypted state files
- Public S3 buckets for state
- State buckets without access logging

**Tradeoffs:** KMS encryption adds cost and complexity; Must manage KMS key access permissions

## PRACTICE: Always use remote state with locking for team environments

**Category:** state_management  |  **Priority:** critical  |  **Level:** beginner

**Why:** Remote state enables collaboration, provides state locking to prevent concurrent modifications, and ensures state is safely backed up and versioned.

```hcl
# Root terragrunt.hcl with S3 backend
remote_state {
  backend = "s3"
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
  config = {
    bucket         = "mycompany-terraform-state"
    key            = "${path_relative_to_include()}/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-state-locks"

    # Prevent accidental bucket deletion
    skip_bucket_versioning = false
  }
}
```

**Antipatterns:**
- Using local state files for shared infrastructure
- Not enabling state locking (DynamoDB for S3)
- Not enabling encryption for state files
- Multiple teams using the same state file

**Tradeoffs:** Additional infrastructure to manage (S3 bucket, DynamoDB table); Costs associated with state storage and locking

## PRACTICE: Use path_relative_to_include() for unique state keys

**Category:** state_management  |  **Priority:** critical  |  **Level:** beginner

**Why:** This function generates unique state file paths based on directory structure, preventing state file collisions and making it clear which infrastructure corresponds to which state.

```hcl
# Root terragrunt.hcl
remote_state {
  backend = "s3"
  config = {
    bucket = "terraform-state"
    key    = "${path_relative_to_include()}/terraform.tfstate"
    # Results in keys like:
    # live/dev/us-east-1/vpc/terraform.tfstate
    # live/prod/us-west-2/eks/terraform.tfstate
  }
}
```

**This one line is a granularity decision, not just a naming convention.** Because the key is
derived per unit, you get **one state file per unit per environment** by default — you do not
have to choose it, and you cannot accidentally share a state between two units. That is the
granularity three independent organisations converge on:

> "you've moved from a 'one state file per environment' model to a 'one state file per
> component, per environment' model. This is a common and highly recommended pattern for mature
> Infrastructure as Code (IaC) management." — docs.terragrunt.com, breaking up a terralith

> "manage resources in separate workspaces when possible, grouping together only necessary and
> logically-related resources... By managing stateful resources independently of stateless
> ones... you limit the blast radius." — HashiCorp, workspace best practices

(Both quotes say "component" or "workspace" where this skill says **unit** — Terragrunt's own
term, and the one used throughout here. A unit is one `terragrunt.hcl`; a **stack** is a set of
units, implicit as a directory tree or explicit as a `terragrunt.stack.hcl`.)

The argument in one sentence, from Gruntwork: *do you want a routine update to a Lambda's
application code to require a plan that also evaluates your production database?* Coupled state
means a mistake in one can reach the other, and every routine change pays the plan time of
everything it is coupled to.

**Antipatterns:**
- Hardcoding state keys
- Using the same state key for different modules
- Manual key construction that can lead to collisions
- One state file for a whole environment. It is the stage teams grow out of, and the symptom is
  that unrelated changes queue behind each other on the same lock.

**Tradeoffs.** The key mirrors the directory structure, which is the point and also the cost:
**moving or renaming a directory moves the state**, and Terragrunt will plan to destroy and
recreate everything in it unless you migrate the state first. That is not a small caveat — it
is the single most expensive mistake available in this area, and it is why the migration
guidance in `architecture-patterns.md` (`## PATTERN: migrate an existing tree to explicit
stacks`) leads with the state-key safety rule rather than the layout. Decide the tree before
you fill it.

Related: `no_dot_terragrunt_stack` on the `stack` block exists precisely to keep
`path_relative_to_include()` stable during a soft migration — see `hcl-blocks.md`.

## PRACTICE: Validate Terragrunt configurations before apply using hooks

**Category:** testing  |  **Priority:** recommended  |  **Level:** intermediate

**Why:** Before hooks can run validation scripts, linters, and policy checks before any Terraform operation, catching errors early.

```hcl
# Root terragrunt.hcl
terraform {
  before_hook "validate" {
    commands = ["apply", "plan"]
    execute  = ["tflint", "--config=.tflint.hcl"]  # requires v1.1.3+ — see note below
  }

  before_hook "security_scan" {
    commands = ["apply"]
    execute  = ["tfsec", "."]
  }
}
```

> **v1.1.3+ for the `--config=` form.** The built-in `tflint` hook reads the config path out
> of the arguments you give it, and before v1.1.3 it recognised only the space-separated
> `--config <path>` spelling. Written as `--config=<path>` the hook behaved as though no
> config had been named at all: it searched the unit directory and its parents for a
> `.tflint.hcl`, then either failed with config-not-found or ran `tflint init` against
> whatever unrelated config the search turned up. **It did not warn.** v1.1.3 accepts
> `--config <path>`, `--config=<path>`, `-c <path>` and `-c=<path>`. On ≤v1.1.2 use the
> space-separated form. v1.1.3 also orders the `--var` arguments the hook builds from
> `inputs` and `TF_VAR_` `extra_arguments` by variable name, so the logged command line is
> stable between runs.

**Antipatterns:**
- Applying without any validation
- Skipping validation in CI to save time
- Not using policy-as-code tools

**Tradeoffs:** Adds time to each operation; Must maintain validation tooling and configs

## PRACTICE: Check inputs against the module's variables before you plan

**Category:** testing  |  **Priority:** recommended  |  **Level:** beginner

**Why:** Catching a missing or mistyped input before `plan` is cheaper than discovering it
during `apply`, and far cheaper than discovering it in a pipeline that has already applied
three units ahead of the broken one.

**The command is `hcl validate --inputs`.** The pre-1.0 `terragrunt validate-inputs` was
removed in v1.0.0 (2026-03-30) and must not be emitted.

```bash
# One unit
terragrunt hcl validate --inputs

# Every unit in the tree
terragrunt run --all -- hcl validate --inputs
```

Note the `--` separator on the second form: `--all` is Terragrunt's flag, `hcl validate
--inputs` is the command being run.

**Antipatterns:**
- Discovering a missing input during `apply`
- Not validating in CI before merge
- Ignoring validation errors because "it planned fine"
- Reaching for `validate-inputs` — it no longer exists

**Tradeoffs:** it adds a step, and it is only as good as the variable definitions in the
module. It cannot tell you an input is *wrong*, only that it is absent or the wrong type. For
what a module actually accepts, use the `terraform-registry` skill.

## COMPARISON: state locking on AWS, Azure and GCP

**The three clouds do not solve this the same way, and only one of them makes you choose.**
Verified against the OpenTofu backend docs and this skill's Azure reference on 2026-08-19.

| backend | mechanism | what you configure |
|---|---|---|
| `s3` | S3 conditional writes (`If-None-Match`), **or** an external DynamoDB table | `use_lockfile = true`, **or** `dynamodb_table` |
| `azurerm` | native blob lease on the state blob | **nothing** |
| `gcs` | native | **nothing** |

**Azure and GCS have no lock table because they never needed one.** The `azurerm` backend takes
a blob lease before any write; there is no second resource to create, no extra IAM to grant and
nothing to forget. GCS likewise — the docs say only "This backend supports state locking", with
no configuration to set. The cost is that a crashed run can leave a lease held: break it with
`az storage blob lease break`. See `azure-backend.md`.

**Only S3 presents a choice, and it is a recent one.** `use_lockfile = true` locks in the state
bucket itself, so there is no DynamoDB table to provision, pay for or grant access to — which is
why it is the sensible default for new work. The older `dynamodb_table` remains correct and is
what most existing estates run.

Be careful how strongly you state this. The docs are explicit:

> "Both S3 and DynamoDB locking mechanisms are fully supported, and the OpenTofu team has no
> plans to deprecate either option. You should choose the locking mechanism that best fits your
> infrastructure requirements."

Only `dynamodb_endpoint` carries a **Deprecated** marker; `dynamodb_table` does not. So:
recommend `use_lockfile` for greenfield, do **not** tell someone their DynamoDB table is
obsolete, and do not call it deprecated — it isn't.

**Migrating S3 from DynamoDB to native locking**, per the documented path — the point is that
both run at once so nobody can take a lock under the old configuration while the change rolls
out:

```hcl
remote_state {
  backend = "s3"
  config = {
    bucket         = "acme-tfstate"
    key            = "${path_relative_to_include()}/tofu.tfstate"
    region         = "eu-west-1"
    use_lockfile   = true            # 1. add alongside the existing table
    dynamodb_table = "acme-tf-locks" # 2. bake; a lock is held only when BOTH succeed
  }                                  # 3. then remove this line
}
```

**One operational caveat on `use_lockfile`.** Locking writes objects into the state bucket, and
the docs recommend versioning on that bucket — so lock objects generate versions too. Add a
lifecycle rule limiting the number of versions. The storage cost is negligible; the version
count is not.

Sources: OpenTofu S3 backend and GCS backend docs, snapshotted 2026-08-19 to
`evals/snapshots/tofu-s3-backend.md` and `tofu-gcs-backend.md`; Azure behaviour from
`references/azure-backend.md`.

## COMPARISON: dependency vs dependencies

dependency defines a single module dependency with output access; dependencies lists modules that must run first without output access.

**Key differences:**
- {'aspect': 'Output Access', 'block1': 'Full access to dependent module outputs', 'block2': 'No output access - ordering only'}
- {'aspect': 'Syntax', 'block1': 'Named block with config_path attribute', 'block2': 'Single block with paths list'}
- {'aspect': 'Performance', 'block1': 'Reads state file to get outputs (slower)', 'block2': 'No state reading required (faster)'}
- {'aspect': 'Mock Support', 'block1': 'Supports mock_outputs for planning', 'block2': 'Not applicable - no outputs to mock'}
- {'aspect': 'Use Case', 'block1': 'When you need values from another module', 'block2': 'When you only need execution ordering'}

**When to use:**
- **useBlock1When**: ['You need to pass outputs from one module to another (e.g., VPC ID)', 'You want to validate configurations with mock values before dependencies exist', 'You need conditional logic based on dependency outputs', 'You want explicit, named references in your inputs block']
- **useBlock2When**: ['You only need to ensure modules run in a specific order', "Performance is critical and you don't need output values", 'You have many dependencies but only need ordering guarantees', "The dependent modules don't expose outputs you need"]

**Common mistakes:**
- Using dependencies when you actually need output values (no outputs.* available)
- Creating dependency blocks for every module when only ordering is needed (performance impact)
- Forgetting mock_outputs when using dependency - causes failures during plan before deps exist
- Circular dependency references between modules

**Official stance & ordering (the DAG):**
Both blocks feed the `run --all` dependency graph, which Terragrunt topologically sorts — apply in dependency order, destroy in reverse. The difference is only what each carries:
- `dependency` adds an ordering edge **and** pulls the target's outputs (`dependency.<name>.outputs.*`).
- `dependencies` adds an ordering edge **only**. Per the docs: *"This does not expose or pull in the outputs like dependency blocks."*

So `dependencies { paths = [...] }` is the **supported, explicit way to force ordering when there is no data/output relationship** — the historical "deploy X before Y regardless" pattern. You're adding an edge the graph wouldn't otherwise infer (inference comes from `dependency` references; there is no implicit ordering without one of these blocks).

Key constraints to set expectations correctly:
- You can only **add** edges, never remove them. There is no weight/priority and no way to tell Terragrunt to *ignore* an edge created by a real `dependency` — to drop an ordering constraint, remove the block that creates it.
- The graph must stay acyclic; a cycle (including one you introduce via `dependencies`) is an error.
- Prefer `dependency` when you need values (it gives ordering for free); reach for `dependencies` purely to sequence units/stacks that don't exchange outputs.

Verified against the official docs: `docs.terragrunt.com/reference/config-blocks-and-attributes` (dependency, dependencies, mock_outputs). See `references/hcl-blocks.md` for the `mock_outputs_*` attributes, including the `mock_outputs_merge_strategy_with_state` values (`no_merge` / `shallow` / `deep_map_only`).

## COMPARISON: include vs multiple includes

A single include inherits from one parent config; multiple includes allow composing configuration from several sources.

**Key differences:**
- {'aspect': 'Composition', 'block1': 'Single source of inherited configuration', 'block2': 'Multiple sources composed together'}
- {'aspect': 'Complexity', 'block1': 'Simple, linear inheritance', 'block2': 'More complex, requires understanding merge order'}
- {'aspect': 'Flexibility', 'block1': "Limited to one parent's configuration", 'block2': 'Mix and match configurations from multiple files'}
- {'aspect': 'Naming', 'block1': 'Name is optional (defaults to empty string)', 'block2': 'Names required to distinguish includes'}
- {'aspect': 'Merge Control', 'block1': 'Single merge with parent', 'block2': 'Per-include merge_strategy control'}

**When to use:**
- **useBlock1When**: ['You have a simple project structure with one root config', 'All shared configuration lives in a single parent file', "You're just starting with Terragrunt and want simplicity", 'Your configuration hierarchy is strictly linear']
- **useBlock2When**: ['You want to separate concerns (env config, region config, common config)', 'Different modules need different combinations of shared configs', 'You have a complex multi-account, multi-region setup', 'You want to compose behavior from reusable config fragments']

**Common mistakes:**
- Not understanding merge order when using multiple includes (last wins for conflicts)
- Forgetting expose = true when trying to access parent locals
- Creating circular include dependencies
- Over-engineering with too many includes when one would suffice

## COMPARISON: inputs vs locals

inputs passes values to Terraform as variables; locals defines reusable values within Terragrunt configuration only.

**Key differences:**
- {'aspect': 'Scope', 'block1': 'Passed to Terraform module', 'block2': 'Only available in Terragrunt config'}
- {'aspect': 'Purpose', 'block1': 'Configure Terraform module behavior', 'block2': 'DRY helper values for Terragrunt'}
- {'aspect': 'Visibility', 'block1': 'Visible in Terraform plan output', 'block2': 'Internal to Terragrunt only'}
- {'aspect': 'Inheritance', 'block1': 'Merged from parent includes', 'block2': 'Must be explicitly exposed to children'}
- {'aspect': 'Reference Syntax', 'block1': 'Used directly in Terraform as var.*', 'block2': 'Referenced as local.* in Terragrunt'}

**When to use:**
- **useBlock1When**: ['Defining values that Terraform needs to configure resources', 'Passing dependency outputs to Terraform', 'Setting environment-specific configuration for modules', 'Any value that needs to reach the Terraform layer']
- **useBlock2When**: ['Computing intermediate values used multiple times', 'Extracting values from file paths or environment', 'Building complex strings or data structures for inputs', 'Defining values shared across multiple inputs']

**Common mistakes:**
- Putting computed values directly in inputs instead of using locals for reuse
- Expecting locals to be available in Terraform (they're not)
- Forgetting that inputs must match Terraform variable declarations
- Not using expose = true in includes when sharing locals

## COMPARISON: generate vs terraform.source

generate creates additional .tf files in the working directory; terraform.source specifies which Terraform module to use.

**Key differences:**
- {'aspect': 'Purpose', 'block1': 'Add configuration to existing module', 'block2': 'Specify which module to run'}
- {'aspect': 'Output', 'block1': 'Creates .tf files in working directory', 'block2': 'Downloads/links module source'}
- {'aspect': 'Common Use', 'block1': 'Providers, backends, common resources', 'block2': 'Module location (registry, git, local)'}
- {'aspect': 'Required', 'block1': 'Optional - only when generating files', 'block2': 'Required - every Terragrunt config needs a source'}
- {'aspect': 'Scope', 'block1': 'Supplements the module', 'block2': 'Defines the module itself'}

**When to use:**
- **useBlock1When**: ["Adding provider configuration to modules that don't include it", 'Dynamically configuring backend based on environment', 'Injecting common resources across all modules', 'Creating files that vary per environment/region']
- **useBlock2When**: ['Always - every Terragrunt module config needs a source', 'Pointing to Terraform Registry modules', 'Using Git repositories for module code', 'Referencing local module directories']

**Common mistakes:**
- Thinking generate replaces terraform.source (they're complementary)
- Generating backend.tf when Terragrunt's remote_state block is better
- Not using if_exists correctly, causing file conflicts
- Forgetting the double-slash in terraform.source for subdirectories

## COMPARISON: before_hook vs after_hook

before_hook runs commands before Terraform; after_hook runs commands after Terraform completes.

**Key differences:**
- {'aspect': 'Timing', 'block1': 'Before Terraform command executes', 'block2': 'After Terraform command completes'}
- {'aspect': 'Abort Behavior', 'block1': 'Failure prevents Terraform from running', 'block2': 'Failure happens after Terraform already ran'}
- {'aspect': 'Common Use Cases', 'block1': 'Validation, setup, pre-flight checks', 'block2': 'Notifications, cleanup, post-processing'}
- {'aspect': 'Error Context', 'block1': "Can't know Terraform result (hasn't run)", 'block2': 'Can react to Terraform success/failure'}
- {'aspect': 'Idempotency', 'block1': 'Should be idempotent (may run multiple times)', 'block2': 'Should handle partial Terraform completion'}

**When to use:**
- **useBlock1When**: ['Validating inputs or environment before Terraform runs', 'Setting up prerequisites (credentials, files)', 'Running pre-flight security or compliance checks', 'Caching or preparing external dependencies']
- **useBlock2When**: ['Sending notifications about apply/destroy results', 'Cleaning up temporary files or resources', 'Triggering downstream processes after changes', 'Logging or auditing Terraform actions']

**Common mistakes:**
- Using after_hook for validation (too late to prevent Terraform)
- Not setting run_on_error = true for cleanup hooks
- Making before_hooks non-idempotent (breaks retries)
- Ignoring hook failures that should abort the operation

## COMPARISON: remote_state vs dependency

remote_state configures where state is stored; dependency references another Terragrunt module's outputs.

**Key differences:**
- {'aspect': 'Purpose', 'block1': "Where to store THIS module's state", 'block2': "How to read ANOTHER module's outputs"}
- {'aspect': 'Direction', 'block1': 'Outbound - writing state', 'block2': 'Inbound - reading state'}
- {'aspect': 'Scope', 'block1': 'One per module (the backend config)', 'block2': 'Multiple per module (one per dependency)'}
- {'aspect': 'State Access', 'block1': 'Configures access credentials and location', 'block2': "Uses dependency's remote_state to read"}
- {'aspect': 'Required', 'block1': 'Required for any module storing state remotely', 'block2': "Only when you need another module's outputs"}

**When to use:**
- **useBlock1When**: ['Configuring where Terraform stores its state file', 'Setting up state locking with DynamoDB/equivalent', 'Enabling encryption for state files', 'Defining consistent state paths across environments']
- **useBlock2When**: ['Passing values between Terragrunt modules', 'Creating execution order based on data flow', 'Reading VPC IDs, ARNs, or other outputs from infrastructure', 'Building a dependency graph for run --all commands']

**Common mistakes:**
- Confusing remote_state (backend config) with dependency (output reading)
- Trying to use dependency to configure where state is stored
- Not realizing dependency reads FROM the other module's remote_state
- Forgetting that remote_state is about YOUR state, dependency is about OTHERS' state

## DECISION: Managing dependencies between Terraform modules

**Question:** How should I manage dependencies between my Terragrunt modules?

**Criteria:**
- {'criterion': 'You need to pass output values from one module to another', 'recommendation': 'Use dependency blocks', 'reason': 'dependency blocks expose .outputs for accessing values like VPC IDs, ARNs, etc.'}
- {'criterion': 'You only need modules to run in a specific order, no data passing', 'recommendation': 'Use dependencies block', 'reason': 'dependencies is lighter weight - no state reading, just ordering'}
- {'criterion': 'You have many dependencies but only need a few outputs', 'recommendation': 'Mix dependency and dependencies', 'reason': 'Use dependency for modules with outputs you need, dependencies for ordering-only'}
- {'criterion': 'You want to plan before dependent modules exist', 'recommendation': 'Use dependency with mock_outputs', 'reason': 'mock_outputs provides fake values for planning without real dependencies'}

- **Explicit Output Dependencies**: Use named dependency blocks for each module whose outputs you need
- **Order-Only Dependencies**: Use dependencies block when you only need execution ordering
- **Hybrid Approach**: Combine both patterns based on actual data needs

## DECISION: DRY configuration inheritance across environments and regions

**Question:** How should I structure configuration inheritance in my Terragrunt project?

**Criteria:**
- {'criterion': 'Simple project with one level of shared config', 'recommendation': 'Use single include with find_in_parent_folders("root.hcl")', 'reason': 'Straightforward inheritance from one root.hcl file'}
- {'criterion': 'Multi-account/multi-region with different config layers', 'recommendation': 'Use multiple named includes', 'reason': 'Compose config from account.hcl, region.hcl, env.hcl, and root.hcl'}
- {'criterion': 'Need to access parent locals in child configs', 'recommendation': 'Use expose = true on include blocks', 'reason': 'Exposes parent locals as include.<name>.locals.*'}
- {'criterion': 'Complex merging requirements', 'recommendation': 'Use merge_strategy per include', 'reason': "Control how each include's values merge with local config"}

- **Simple Root Include**: Single parent file for all shared configuration
- **Layered Includes**: Multiple include files for different concerns
- **Environment-Specific Overrides**: Common base with environment-specific configurations

## DECISION: Configuring Terraform state storage and backend

**Question:** How should I configure my Terraform backend in Terragrunt?

**Criteria:**
- {'criterion': 'Need automatic backend configuration with state locking', 'recommendation': 'Use remote_state with generate = true', 'reason': 'Terragrunt generates backend.tf and can create bucket/table automatically'}
- {'criterion': 'Backend already configured in Terraform module', 'recommendation': 'Use remote_state with generate = false or skip it', 'reason': 'Avoid conflicts with existing backend configuration'}
- {'criterion': 'Different backends for different environments', 'recommendation': 'Define remote_state in environment-level includes', 'reason': 'Each env can have its own state bucket/configuration'}
- {'criterion': 'Need to reference state from other modules', 'recommendation': 'Use dependency blocks, not direct state access', 'reason': 'dependency provides typed access to outputs with mock support'}

- **Centralized S3 Backend**: Single state bucket with path-based keys
- **Per-Environment Backends**: Separate state storage per environment
- **Workspaces Alternative**: Use Terragrunt directory structure instead of Terraform workspaces
