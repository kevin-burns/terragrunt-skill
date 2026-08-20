# Advanced Terragrunt Examples

> Source: curated data harvested from omattsson/terragrunt-mcp-server, restructured for grep-based lookup.
> Content spot-checked against docs.terragrunt.com at **v1.1.0** (2026-07-01); reviewed against the **v1.1.1** release notes (2026-07-14) on 2026-07-29 with no changes required — v1.1.1 was bug-fix only, and its two new experiments touch the `terraform` block (see hcl-blocks.md). Flag and avoid any pre-1.0 idioms.

Lookup: `grep -n '^## EXAMPLE:' advanced-examples.md`

## Contents
- Basic Cross-Module Dependency (dependencies, basic)
- Complex Dependency Graph (dependencies, advanced)
- Conditional Dependency Skipping (dependencies, intermediate)
- Conditional File Generation (generate, advanced)
- DRY Locals Pattern (dry-patterns, basic)
- Dynamic Backend Generation (generate, intermediate)
- Dynamic Provider Generation (generate, intermediate)
- Environment Feature Flags (environment, intermediate)
- Environment Variable Merging (environment, intermediate)
- Error Handling Hooks (hooks, advanced)
- Exposed Include for Overrides (dry-patterns, intermediate)
- Hierarchical Environment Configuration (environment, advanced)
- Mock Outputs for Dependencies (dependencies, intermediate)
- Multi-Command Hook Pipeline (hooks, advanced)
- Multiple Includes Pattern (dry-patterns, intermediate)
- Post-Apply Notification Hook (hooks, intermediate)
- Pre-Apply Validation Hook (hooks, intermediate)
- Read Terragrunt Config Pattern (dry-patterns, intermediate)
- Root Include Pattern (dry-patterns, basic)
- Version Constraints Generation (generate, basic)
- Workspace-Based Environment Selection (environment, intermediate)

## EXAMPLE: Integrate a module you wrote yourself

**Category:** modules  |  **Complexity:** basic  |  Tags: source, own-module, git, monorepo, pinning

Most Terragrunt material assumes you are consuming somebody else's registry module. The common
real case is a module your team wrote. Terragrunt does not care who wrote it — what changes is
**where it lives**, and that decides the `source` syntax and the pinning strategy.

**Three layouts, three sources:**

```hcl
# 1. Module in its own repo — the usual choice once more than one team consumes it.
#    `//` separates the repo from the path INSIDE it. `?ref=` is the git ref.
terraform {
  source = "git::ssh://git@github.com/acme/terraform-modules.git//vpc?ref=v1.4.0"
}

# 2. Module in the SAME repo as the live config.
#    No fetch, no ref, no tag to cut. Good while a module has exactly one consumer.
#    ANCHOR TO THE CONFIG HIERARCHY, NOT TO GIT AND NOT TO A COUNT OF `../`.
terraform {
  source = "${dirname(find_in_parent_folders("root.hcl"))}//modules/vpc"
}
#    A bare "../../../modules/vpc" encodes how deep this unit happens to sit, so it breaks the
#    day someone adds a region or environment level. `get_repo_root()` and
#    `get_path_to_repo_root()` look like the fix and are worse: both walk up to `.git`, so they
#    resolve differently — or error — in an exported artifact, a partial CI checkout, or a
#    monorepo where the git root sits above the infrastructure root. That failure is
#    environment-dependent: correct locally, wrong in the pipeline. See `functions.md`.

# 3. Module in a private registry.
#    Name the host: a bare `tfr:///` follows the wrapped engine (see `## BLOCK: terraform`).
terraform {
  source = "tfr://registry.example.com/acme/vpc/aws?version=1.4.0"
}
```

**Pin to a tag, never a branch.** `?ref=main` means the module can change between your plan and
your apply, and can differ between the run that deployed staging and the run that deployed
production an hour later. `?ref=v1.4.0` is reproducible; a commit SHA is more so and is uglier.
The reason this matters more for your own module than for a registry one is that your own module
changes far more often, and often while you are mid-rollout.

**The trade-off between 1 and 2 is not style.** A relative path costs nothing and updates
instantly, which is exactly the problem: every environment moves the moment the module changes,
because there is no version to hold prod back while you test in dev. A separate repo forces a
tag, and the tag is what lets environments sit on different versions. Split when you need that,
not before.

If you keep the module in the same repo and use it from a catalog, `update_source_with_cas`
rewrites the relative source into a content-addressed reference at stack generation — but the
`source` must be a literal string, and `--no-cas` must not be set. See `## BLOCK: terraform`.

**Local modules are copied, not linked.** Terragrunt copies the source into
`.terragrunt-cache`, so files beside the module are not automatically present. `include_in_copy`
and `exclude_from_copy` on the `terraform` block control that, and they are **not** mutually
exclusive — a file matching both is excluded.

## EXAMPLE: Iterate on your own module without cutting a release

**Category:** modules  |  **Complexity:** intermediate  |  Tags: source, source-map, local-development

The friction with layout 1 above is the loop: edit module, commit, tag, bump the `ref` in the
unit, run. Terragrunt has two overrides so you do not have to.

**`--source` replaces the source outright, for one run:**

```bash
terragrunt run plan --source ../../../modules/vpc
```

> "This overrides any `source` parameters specified in the Terragrunt configuration files."

Simple, and it only helps one unit — you are naming a single path.

**`--source-map` rewrites matching URLs across the whole run**, which is what you want for
`run --all`:

```bash
terragrunt run --all   --source-map "git::ssh://git@github.com/acme/terraform-modules.git=../../terraform-modules"   -- plan
```

It "affects both direct source references and sources specified in dependency blocks", so a
whole tree points at your working copy without a single file being edited. Also available as
`TG_SOURCE_MAP`.

**THE TRAP, and it fails silently.** From the docs:

> "Source mapping only performs literal matches on the URL portion. For example, a map key of
> `ssh://git@github.com/org/repo.git` will not match sources of the form
> `git::ssh://git@github.com/org/repo.git`. The latter requires a map key of
> `git::ssh://git@github.com/org/repo.git`."

A key that does not match produces **no error**. Terragrunt fetches the real module from git,
the plan succeeds, and you spend the next twenty minutes wondering why your edit had no effect.
**Copy the `source` string out of the config verbatim, `git::` prefix and all, and use that as
the key.**

**And clear the cache when the source changes shape:**

```bash
terragrunt run plan --source-update
```

> "Delete the contents of the temporary folder to clear out any old, cached source code before
> downloading new source code into it."

Verified against docs.terragrunt.com/reference/cli/commands/run/ on 2026-08-19.

## EXAMPLE: GCP project-per-environment, with the project derived from the tree

**Category:** gcp  |  **Complexity:** intermediate  |  Tags: gcp, google, project, multi-project, provider

GCP's isolation boundary is the **project**, so the shape that maps onto an AWS multi-account
or Azure multi-subscription estate is multi-project. The trap is specific to GCP and worth
stating first.

**Every argument on the `google` provider is optional, and there is no `allowed_account_ids`.**
AWS lets you assert which account a unit may touch; azurerm v4 makes `subscription_id`
mandatory. GCP has neither. An unset `project` falls back to `GOOGLE_PROJECT`, then to
Application Default Credentials, then to whatever `gcloud config set project` last pointed at.
The plan succeeds against the wrong project and nothing warns.

**So derive the project from the path and never type it in a unit.**

```
live/
├── root.hcl                      # backend + generated provider
├── prod/
│   ├── env.hcl                   # locals { project_id = "acme-prod-1a2b", environment = "prod" }
│   └── europe-west2/
│       ├── region.hcl            # locals { region = "europe-west2" }
│       ├── network/terragrunt.hcl
│       └── storage/terragrunt.hcl
└── nonprod/
    ├── env.hcl                   # locals { project_id = "acme-nonprod-3c4d" }
    └── europe-west2/...
```

```hcl
# root.hcl — the project comes from the tree, so the path and the target cannot disagree
locals {
  env_vars    = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  region_vars = read_terragrunt_config(find_in_parent_folders("region.hcl"))
  project_id  = local.env_vars.locals.project_id
  region      = local.region_vars.locals.region
}

generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<PROVIDER
provider "google" {
  project = "${local.project_id}"
  region  = "${local.region}"
}
PROVIDER
}

remote_state {
  backend = "gcs"
  config = {
    bucket = "acme-tfstate-${local.env_vars.locals.environment}"
    prefix = path_relative_to_include()
  }
}
```

See `templates/providers/gcp-generate-provider.hcl` for the fuller version, including
impersonation and the `user_project_override` / `billing_project` pairing.

## EXAMPLE: Wrapping Cloud Foundation Toolkit modules

**Category:** gcp  |  **Complexity:** basic  |  Tags: gcp, google, cft, module, dependency

Google's equivalent of Azure's AVM is the **Cloud Foundation Toolkit** — the
`terraform-google-modules/*` and `GoogleCloudPlatform/*` namespaces on the public registry.
Unlike AVM these are **past 1.0**, so a major version means what semver says it means.
Verified on **2026-08-19**:

| module | version | required inputs |
|---|---|---|
| `terraform-google-modules/network/google` | 18.1.2 | `project_id`, `network_name`, `subnets` |
| `terraform-google-modules/project-factory/google` | 18.3.0 | 2 |
| `terraform-google-modules/cloud-storage/google` | 12.3.0 | `project_id`, `names` |
| `GoogleCloudPlatform/lb-http/google` | 14.2.0 | 3 |

**`project_id` is a required input on the modules themselves**, not merely a provider default —
so it is passed twice, and the two must agree. Deriving both from the same local is the point
of the previous example.

```hcl
# live/prod/europe-west2/storage/terragrunt.hcl
terraform {
  source = "tfr://registry.terraform.io/terraform-google-modules/cloud-storage/google?version=12.3.0"
}

include "root" { path = find_in_parent_folders("root.hcl") }

locals {
  env_vars = read_terragrunt_config(find_in_parent_folders("env.hcl"))
}

dependency "network" {
  config_path = "../network"

  mock_outputs = {
    network_name = "mock-vpc"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

inputs = {
  project_id = local.env_vars.locals.project_id
  names      = ["acme-prod-artifacts", "acme-prod-logs"]
  location   = "EUROPE-WEST2"
}
```

**Pin the registry host.** A bare `tfr:///` resolves to `registry.terraform.io` under Terraform
and `registry.opentofu.org` under OpenTofu, and the OpenTofu registry is populated
independently rather than mirrored — a version present on one may be absent from the other. See
`## BLOCK: terraform` in `hcl-blocks.md`.

For a module's current version, required inputs or a resource's attributes, use the
`terraform-registry` skill — it covers the google provider (1,344 resources cached) as well as
aws and azurerm.

## EXAMPLE: Wrap an Azure Verified Module in a Terragrunt unit

**Category:** azure  |  **Complexity:** basic  |  Tags: azure, avm, module, source, unit

AVM is Microsoft's set of pre-built, WAF-aligned Azure modules. They are ordinary registry
modules, so a Terragrunt unit wraps one exactly as it wraps any other — the value is that the
defaults are the ones Microsoft recommends rather than the ones the provider ships.

**Two classes, and the names tell you which you have:**

| class | registry name | what it deploys |
|---|---|---|
| Resource module | `avm-res-<provider>-<resourcetype>` | one primary resource, with WAF defaults set |
| Pattern module | `avm-ptn-<name>` | several resources, usually composed from resource modules |

All published under the `Azure/` namespace on the public Terraform registry.

```hcl
# live/prod/uksouth/network/terragrunt.hcl
terraform {
  source = "tfr://registry.terraform.io/Azure/avm-res-network-virtualnetwork/azurerm?version=0.22.1"
}

include "root" {
  path = find_in_parent_folders("root.hcl")
}

dependency "rg" {
  config_path = "../resource-group"
}

inputs = {
  parent_id     = dependency.rg.outputs.resource_id
  location      = "uksouth"
  name          = "vnet-prod-uksouth"
  address_space = ["10.20.0.0/16"]

  # AVM ships a telemetry module on by default. Many enterprises turn it off.
  enable_telemetry = false
}
```

**Pin the host, not just the version.** A bare `tfr:///` resolves to `registry.terraform.io`
under Terraform and `registry.opentofu.org` under OpenTofu, and the OpenTofu registry is not a
mirror — see `## BLOCK: terraform` in `hcl-blocks.md`. AVM publishes to the Terraform registry;
name it.

**Find the module rather than guessing its name.** Microsoft publishes a machine-readable
index — `https://azure.github.io/Azure-Verified-Modules/module-indexes/TerraformResourceModules.csv`
— which carried 158 resource modules on 2026-08-19. For inputs, outputs and current versions,
use the `terraform-registry` skill rather than reading registry JSON by hand.

## EXAMPLE: The AVM interface is not uniform — check every module's required inputs

**Category:** azure  |  **Complexity:** intermediate  |  Tags: azure, avm, inputs, trap

**Do not assume AVM modules share a shape.** They are versioned independently and the interface
has moved over time. Eight resource modules sampled from the registry on **2026-08-19**:

| module | version | required inputs |
|---|---|---|
| `avm-res-resources-resourcegroup` | 0.4.0 | `name`, `location` |
| `avm-res-network-virtualnetwork` | 0.22.1 | **`parent_id`**, `location` — `name` is *optional* |
| `avm-res-storage-storageaccount` | 0.9.0 | **`parent_id`**, `name`, `location` |
| `avm-res-containerservice-managedcluster` | 0.8.1 | **`parent_id`**, `name`, `location` |
| `avm-res-keyvault-vault` | 0.11.0 | **`resource_group_name`**, `name`, `location`, `tenant_id` |
| `avm-res-network-networksecuritygroup` | 0.5.1 | **`resource_group_name`**, `name`, `location` |
| `avm-res-operationalinsights-workspace` | 0.5.1 | **`resource_group_name`**, `name`, `location` |
| `avm-res-compute-virtualmachine` | 0.21.0 | **`resource_group_name`**, `name`, `location`, `zone` |

**Of the seven that need a containing resource group, three take `parent_id` and four take
`resource_group_name`.** That is a coin flip, not a migration edge case — you cannot infer one
module's spelling from another's. `compute-virtualmachine` additionally requires a `zone` that
no other module in the sample does, and `network-virtualnetwork` — where you would most expect
a name — is the only one where `name` is optional.

**Every module here is still 0.x**, from 0.4.0 to 0.22.1. None of them owes you interface
stability under semver, and a minor bump can move a required input.

```hcl
# WRONG — assumes keyvault takes parent_id like its siblings
inputs = {
  parent_id = dependency.rg.outputs.resource_id   # keyvault does not accept this
  name      = "kv-prod-uksouth"
}

# RIGHT — check the module you are actually calling
inputs = {
  resource_group_name = dependency.rg.outputs.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  name                = "kv-prod-uksouth"
  location            = "uksouth"
}
```

The failure is a plan-time "Unsupported argument" or a missing-required-argument error, so it
does not reach apply — but it costs a cycle per module, and it recurs every time a module is
upgraded across the migration. **Check the required inputs at the version you are pinning**,
with `terraform-registry`, before writing the unit.

## EXAMPLE: Multi-subscription Azure estate, resource group first

**Category:** azure  |  **Complexity:** advanced  |  Tags: azure, multi-subscription, dependency, avm, layout

Azure's analogue of AWS multi-account is multi-subscription, and the ordering constraint is
firmer: almost everything lives inside a resource group, so the resource group unit is a
dependency of nearly every sibling.

```
live/
├── root.hcl                          # backend + azurerm provider, subscription_id from the tree
├── prod/
│   ├── subscription.hcl              # subscription_id, tenant_id for this scope
│   └── uksouth/
│       ├── region.hcl
│       ├── resource-group/terragrunt.hcl     # avm-res-resources-resourcegroup
│       ├── network/terragrunt.hcl            # avm-res-network-virtualnetwork  -> depends on rg
│       ├── keyvault/terragrunt.hcl           # avm-res-keyvault-vault          -> depends on rg
│       └── storage/terragrunt.hcl            # avm-res-storage-storageaccount  -> depends on rg
└── nonprod/
    ├── subscription.hcl
    └── uksouth/...
```

```hcl
# live/prod/uksouth/storage/terragrunt.hcl
terraform {
  source = "tfr://registry.terraform.io/Azure/avm-res-storage-storageaccount/azurerm?version=0.9.0"
}

include "root" { path = find_in_parent_folders("root.hcl") }

dependency "rg" {
  config_path = "../resource-group"

  # So `run --all plan` works before anything is applied.
  mock_outputs = {
    resource_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/mock"
    name        = "rg-mock"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

inputs = {
  parent_id                = dependency.rg.outputs.resource_id
  name                     = "stprodukso001"
  location                 = "uksouth"
  account_tier             = "Standard"
  account_replication_type = "ZRS"
  enable_telemetry         = false
}
```

**The Azure-specific traps are in `azure-backend.md`, not here** — a data-plane RBAC role is
required for blob state and ARM Owner or Contributor is *not* sufficient, the provider needs
`subscription_id` on v4, and shared-key-disabled storage returns 403 unless `use_azuread_auth`
is set. Read that file for any Azure backend or provider work; this example assumes it is
already right.

## EXAMPLE: Basic Cross-Module Dependency

**Category:** dependencies  |  **Complexity:** basic  |  Tags: dependency, outputs, cross-module, vpc

Reference outputs from another Terragrunt module

```hcl
# Define dependency on VPC module
dependency "vpc" {
  config_path = "../vpc"
}

# Define dependency on security groups module
dependency "security_groups" {
  config_path = "../security-groups"
}

inputs = {
  # Use outputs from dependencies
  vpc_id            = dependency.vpc.outputs.vpc_id
  subnet_ids        = dependency.vpc.outputs.private_subnet_ids
  security_group_id = dependency.security_groups.outputs.app_sg_id
}
```

**Use cases:** Share VPC IDs across multiple modules; Reference security group IDs; Chain module deployments in correct order

**Pitfalls:**
- Circular dependencies cause errors
- Output changes can break dependent modules
- Long dependency chains slow down planning

## EXAMPLE: Complex Dependency Graph

**Category:** dependencies  |  **Complexity:** advanced  |  Tags: dependency, graph, multi-level, diamond, complex

Multi-level dependencies with diamond pattern handling

```hcl
# This module depends on multiple modules that share common dependencies
# Dependency graph:
#
#     network
#    /       \
#   db       cache
#    \       /
#      app (this module)

dependency "network" {
  config_path = "../network"
}

dependency "database" {
  config_path = "../database"

  # Database depends on network, but we also need network
  # Terragrunt handles this automatically
}

dependency "cache" {
  config_path = "../cache"

  # Cache also depends on network
}

locals {
  # Aggregate outputs from all dependencies
  all_security_groups = concat(
    [dependency.database.outputs.security_group_id],
    [dependency.cache.outputs.security_group_id]
  )
}

inputs = {
  vpc_id                  = dependency.network.outputs.vpc_id
  subnet_ids              = dependency.network.outputs.app_subnet_ids

  database_endpoint       = dependency.database.outputs.endpoint
  database_port           = dependency.database.outputs.port

  cache_endpoint          = dependency.cache.outputs.endpoint
  cache_port              = dependency.cache.outputs.port

  allowed_security_groups = local.all_security_groups
}

# Specify explicit dependencies for destroy ordering
dependencies {
  paths = ["../network", "../database", "../cache"]
}
```

**Use cases:** Microservices with shared infrastructure; Applications with multiple data stores; Complex multi-tier architectures

**Pitfalls:**
- Deep graphs slow down terragrunt run --all plan
- Circular dependencies are forbidden
- Changes to shared dependencies affect many modules

## EXAMPLE: Conditional Dependency Skipping

**Category:** dependencies  |  **Complexity:** intermediate  |  Tags: dependency, skip, destroy, conditional

Skip dependencies in specific scenarios like destroy or first deployment

```hcl
dependency "vpc" {
  config_path = "../vpc"

  # Skip dependency during destroy to avoid order issues
  skip_outputs = true
}

# Alternative: Use locals to conditionally handle dependencies
locals {
  # Check if this is a destroy operation
  is_destroy = get_env("TG_COMMAND", "") == "destroy"

  # Check if VPC module has been applied
  vpc_exists = fileexists("${get_terragrunt_dir()}/../vpc/.terragrunt-cache")
}

dependency "database" {
  config_path = "../rds"

  # Skip outputs during destroy or if not yet created
  skip_outputs = local.is_destroy

  mock_outputs = {
    endpoint = "localhost:5432"
  }
  mock_outputs_allowed_terraform_commands = ["validate", "plan", "destroy"]
}

inputs = {
  # Handle case where dependency outputs might not exist
  database_endpoint = local.is_destroy ? "" : dependency.database.outputs.endpoint
}
```

**Use cases:** Destroy resources in correct order; First-time deployment of new environments; Handling optional dependencies

**Pitfalls:**
- Skipping can mask real dependency issues
- State may become inconsistent
- Test skip scenarios carefully

## EXAMPLE: Mock Outputs for Dependencies

**Category:** dependencies  |  **Complexity:** intermediate  |  Tags: dependency, mock, outputs, plan, development

Define mock outputs to enable plan without applying dependencies

```hcl
dependency "vpc" {
  config_path = "../vpc"

  # Mock outputs for planning when VPC doesn't exist yet
  mock_outputs = {
    vpc_id             = "vpc-mock-12345"
    private_subnet_ids = ["subnet-mock-1", "subnet-mock-2"]
    public_subnet_ids  = ["subnet-mock-3", "subnet-mock-4"]
    vpc_cidr_block     = "10.0.0.0/16"
  }

  # Only use mocks when allowed (not in production)
  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
  mock_outputs_merge_strategy_with_state  = "shallow"
}

dependency "database" {
  config_path = "../rds"

  mock_outputs = {
    endpoint        = "mock-db.example.com:5432"
    connection_url  = "postgresql://mock:mock@mock-db.example.com:5432/app"
    read_replica_endpoints = []
  }

  mock_outputs_allowed_terraform_commands = ["validate", "plan"]
}

inputs = {
  vpc_id          = dependency.vpc.outputs.vpc_id
  subnet_ids      = dependency.vpc.outputs.private_subnet_ids
  database_url    = dependency.database.outputs.connection_url
}
```

**Use cases:** Run terraform plan without applying dependencies first; Faster development feedback loops; CI validation of individual modules

**Pitfalls:**
- Mocks can hide dependency issues until apply
- Mock values that pass validation may fail at apply
- Don't allow mocks for apply commands

## EXAMPLE: DRY Locals Pattern

**Category:** dry-patterns  |  **Complexity:** basic  |  Tags: locals, DRY, naming, conditional, parsing

Compute derived values in locals to avoid repetition

```hcl
locals {
  # Parse environment from directory structure
  # Example path: live/production/us-east-1/app/web-server
  path_parts  = split("/", path_relative_to_include())
  environment = local.path_parts[0]  # production
  region      = local.path_parts[1]  # us-east-1
  app_name    = local.path_parts[2]  # app
  module_name = local.path_parts[3]  # web-server

  # Derive resource naming convention
  name_prefix = "${local.environment}-${local.region}-${local.app_name}"
  full_name   = "${local.name_prefix}-${local.module_name}"

  # Common tags derived from parsed values
  common_tags = {
    Environment = local.environment
    Region      = local.region
    Application = local.app_name
    Module      = local.module_name
    ManagedBy   = "Terragrunt"
    FullName    = local.full_name
  }

  # Conditional values based on environment
  is_production = local.environment == "production"

  instance_settings = local.is_production ? {
    instance_type = "m5.large"
    min_size      = 3
    max_size      = 10
  } : {
    instance_type = "t3.micro"
    min_size      = 1
    max_size      = 2
  }
}

inputs = {
  name          = local.full_name
  instance_type = local.instance_settings.instance_type
  min_size      = local.instance_settings.min_size
  max_size      = local.instance_settings.max_size
  tags          = local.common_tags
}
```

**Use cases:** Derive values from directory structure; Consistent naming conventions; Environment-conditional configurations

**Pitfalls:**
- Path parsing is fragile to structure changes
- Complex locals are hard to debug
- Don't repeat logic that belongs in modules

## EXAMPLE: Exposed Include for Overrides

**Category:** dry-patterns  |  **Complexity:** intermediate  |  Tags: include, expose, override, defaults, template

Expose included configurations and selectively override

```hcl
# _envcommon/service.hcl - shared service configuration
locals {
  # Default service configuration
  default_cpu    = 256
  default_memory = 512
  default_port   = 8080

  health_check = {
    path     = "/health"
    interval = 30
    timeout  = 5
  }
}

terraform {
  source = "git::git@github.com:my-org/terraform-modules.git//ecs-service?ref=v1.0.0"
}

# -------------------------------------------
# In module terragrunt.hcl:

include "root" {
  path = find_in_parent_folders("root.hcl")
}

include "service" {
  path   = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/service.hcl"
  expose = true
}

locals {
  # Override specific values while keeping defaults
  cpu    = 512  # Override: need more CPU
  memory = include.service.locals.default_memory  # Keep default
  port   = include.service.locals.default_port    # Keep default

  # Deep merge health check with overrides
  health_check = merge(
    include.service.locals.health_check,
    {
      path = "/api/health"  # Custom health endpoint
    }
  )
}

inputs = {
  cpu          = local.cpu
  memory       = local.memory
  port         = local.port
  health_check = local.health_check
}
```

**Use cases:** Define service templates with defaults; Override specific values per module; Share configuration across similar modules

**Pitfalls:**
- Exposed locals create coupling
- Changing defaults affects all consumers
- Type mismatches between override and default

## EXAMPLE: Multiple Includes Pattern

**Category:** dry-patterns  |  **Complexity:** intermediate  |  Tags: include, multiple, compose, DRY, merge

Include configurations from multiple parent files

```hcl
# Multiple includes allow composing configurations from different sources

# Include the root configuration
include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

# Include environment-specific configuration
include "env" {
  path   = find_in_parent_folders("env.hcl")
  expose = true
}

# Include module-type specific configuration (e.g., for all ECS services)
include "ecs" {
  path           = "${get_terragrunt_dir()}/../../_modules/ecs-service.hcl"
  expose         = true
  merge_strategy = "deep"
}

locals {
  # Access exposed values from includes
  environment = include.env.locals.environment
  aws_region  = include.env.locals.aws_region
  common_tags = include.root.locals.common_tags

  # ECS-specific settings from module include
  ecs_cluster = include.ecs.locals.cluster_name
}

inputs = {
  environment  = local.environment
  region       = local.aws_region
  cluster_name = local.ecs_cluster

  tags = merge(
    local.common_tags,
    {
      Environment = local.environment
      Service     = "my-service"
    }
  )
}
```

**Use cases:** Compose configurations from multiple sources; Share module-type-specific configurations; Separate concerns across different config files

**Pitfalls:**
- Include order affects merge behavior
- Can be hard to trace where values come from
- Avoid deeply nested includes

## EXAMPLE: Read Terragrunt Config Pattern

**Category:** dry-patterns  |  **Complexity:** intermediate  |  Tags: read_terragrunt_config, lookup, shared, data, DRY

Use read_terragrunt_config for selective configuration reuse

```hcl
# _shared/common.hcl - shared configuration (not included, just read)
locals {
  aws_account_ids = {
    dev        = "111111111111"
    staging    = "222222222222"
    production = "333333333333"
  }

  vpc_cidrs = {
    dev        = "10.0.0.0/16"
    staging    = "10.1.0.0/16"
    production = "10.2.0.0/16"
  }

  database_configs = {
    dev = {
      instance_class = "db.t3.micro"
      multi_az       = false
    }
    staging = {
      instance_class = "db.t3.small"
      multi_az       = false
    }
    production = {
      instance_class = "db.r5.large"
      multi_az       = true
    }
  }
}

# -------------------------------------------
# In module terragrunt.hcl:

locals {
  # Read environment from folder structure
  env_config  = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  environment = local.env_config.locals.environment

  # Read shared configuration
  shared = read_terragrunt_config(
    "${dirname(find_in_parent_folders("root.hcl"))}/_shared/common.hcl"
  )

  # Look up values for current environment
  account_id = local.shared.locals.aws_account_ids[local.environment]
  vpc_cidr   = local.shared.locals.vpc_cidrs[local.environment]
  db_config  = local.shared.locals.database_configs[local.environment]
}

inputs = {
  account_id     = local.account_id
  vpc_cidr       = local.vpc_cidr
  instance_class = local.db_config.instance_class
  multi_az       = local.db_config.multi_az
}
```

**Use cases:** Lookup tables for environment-specific values; Shared constants without full include; Selective reuse of specific configurations

**Pitfalls:**
- File must exist or terragrunt fails
- No dependency tracking between read files
- Can't use all HCL features in read files

## EXAMPLE: Root Include Pattern

**Category:** dry-patterns  |  **Complexity:** basic  |  Tags: include, root, DRY, remote-state, common

Include common configuration from a root terragrunt.hcl

```hcl
# root.hcl at repository root
locals {
  # Common tags for all resources
  common_tags = {
    ManagedBy   = "Terragrunt"
    Repository  = "my-infrastructure"
    LastUpdated = timestamp()
  }
}

# Remote state configuration (inherited by all modules)
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

# -------------------------------------------
# In child module terragrunt.hcl:

include "root" {
  path = find_in_parent_folders("root.hcl")
}

locals {
  root_config = read_terragrunt_config(find_in_parent_folders("root.hcl"))
}

inputs = {
  tags = local.root_config.locals.common_tags
}
```

**Use cases:** Centralize remote state configuration; Share common tags across all modules; Define organization-wide defaults

**Pitfalls:**
- Changes to root affect all modules
- Overriding root settings can be confusing
- Test root changes in non-production first

## EXAMPLE: Environment Feature Flags

**Category:** environment  |  **Complexity:** intermediate  |  Tags: environment, feature-flags, toggle, configuration

Toggle features based on environment using configuration flags

```hcl
locals {
  env_config = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  environment = local.env_config.locals.environment

  # Feature flags per environment
  feature_flags = {
    dev = {
      enable_debug_logging = true
      enable_encryption    = false
      enable_backups       = false
      enable_monitoring    = false
      enable_waf           = false
    }
    staging = {
      enable_debug_logging = true
      enable_encryption    = true
      enable_backups       = true
      enable_monitoring    = true
      enable_waf           = false
    }
    production = {
      enable_debug_logging = false
      enable_encryption    = true
      enable_backups       = true
      enable_monitoring    = true
      enable_waf           = true
    }
  }

  # Get flags for current environment
  flags = local.feature_flags[local.environment]
}

inputs = {
  enable_debug_logging = local.flags.enable_debug_logging
  enable_encryption    = local.flags.enable_encryption
  enable_backups       = local.flags.enable_backups
  enable_monitoring    = local.flags.enable_monitoring
  enable_waf           = local.flags.enable_waf
}
```

**Use cases:** Gradually roll out features to production; Reduce costs in non-production environments; Toggle security features per environment

**Pitfalls:**
- Too many flags increase complexity
- Feature parity issues between environments
- Forgetting to enable critical features in production

## EXAMPLE: Environment Variable Merging

**Category:** environment  |  **Complexity:** intermediate  |  Tags: environment, merge, variables, overrides, defaults

Merge variables from multiple configuration files with overrides

```hcl
locals {
  # Default values (lowest priority)
  defaults = {
    instance_type = "t3.micro"
    min_size      = 1
    max_size      = 3
    enable_ha     = false
  }

  # Environment-specific overrides
  env_config = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  env_vars   = try(local.env_config.locals.app_config, {})

  # Module-specific overrides (highest priority)
  module_vars = {
    # Override specific values for this module
    min_size = 2
  }

  # Merge all configurations
  # Order matters: later maps override earlier ones
  config = merge(
    local.defaults,
    local.env_vars,
    local.module_vars
  )
}

inputs = {
  instance_type = local.config.instance_type
  min_size      = local.config.min_size
  max_size      = local.config.max_size
  enable_ha     = local.config.enable_ha
}
```

**Use cases:** Define sensible defaults with environment overrides; Allow module-specific customizations; Reduce duplication across similar modules

**Pitfalls:**
- Deep merge doesn't merge nested maps by default
- Can be hard to trace where a value came from
- Type mismatches cause confusing errors

## EXAMPLE: Hierarchical Environment Configuration

**Category:** environment  |  **Complexity:** advanced  |  Tags: environment, hierarchy, multi-account, organization

Multi-level configuration hierarchy for root/account/region/environment

```hcl
# In each terragrunt.hcl, merge configurations from the hierarchy

locals {
  # Parse the file path to extract environment components
  parsed = regex(".*/(?P<account>.*)/(?P<region>.*)/(?P<env>.*)/(?P<module>.*)$", get_terragrunt_dir())

  # Load configs from each level of the hierarchy
  root_config    = read_terragrunt_config(find_in_parent_folders("root.hcl"))
  account_config = read_terragrunt_config(find_in_parent_folders("account.hcl"))
  region_config  = read_terragrunt_config(find_in_parent_folders("region.hcl"))
  env_config     = read_terragrunt_config(find_in_parent_folders("env.hcl"))

  # Merge configurations (later values override earlier)
  merged_tags = merge(
    local.root_config.locals.tags,
    local.account_config.locals.tags,
    local.region_config.locals.tags,
    local.env_config.locals.tags,
    {
      Module = local.parsed.module
    }
  )

  # Extract commonly used values
  account_id  = local.account_config.locals.account_id
  aws_region  = local.region_config.locals.aws_region
  environment = local.env_config.locals.environment
}

# Include the root configuration
include "root" {
  path = find_in_parent_folders("root.hcl")
}

inputs = {
  tags = local.merged_tags
}
```

**Use cases:** Manage multi-account AWS organizations; Support multiple regions with consistent config; Layer configurations from global to specific

**Pitfalls:**
- Deep hierarchies become complex to debug
- Circular dependencies can occur with complex includes
- Performance impact from reading many files

## EXAMPLE: Workspace-Based Environment Selection

**Category:** environment  |  **Complexity:** intermediate  |  Tags: environment, workspace, isolation, TF_WORKSPACE

Use Terraform workspaces with Terragrunt for environment isolation

```hcl
locals {
  # Map workspace names to environment configurations
  workspace_configs = {
    default = {
      environment   = "dev"
      instance_type = "t3.micro"
      replica_count = 1
    }
    staging = {
      environment   = "staging"
      instance_type = "t3.small"
      replica_count = 2
    }
    production = {
      environment   = "production"
      instance_type = "t3.large"
      replica_count = 3
    }
  }

  # Get current workspace or default
  workspace = get_env("TF_WORKSPACE", "default")

  # Select configuration for current workspace
  config = lookup(local.workspace_configs, local.workspace, local.workspace_configs["default"])
}

inputs = {
  environment   = local.config.environment
  instance_type = local.config.instance_type
  replica_count = local.config.replica_count

  tags = {
    Environment = local.config.environment
    Workspace   = local.workspace
  }
}
```

**Use cases:** Test infrastructure changes before production; Quick environment switching for development; CI/CD pipelines with workspace-based deployments

**Pitfalls:**
- Workspaces share the same backend configuration
- Easy to accidentally apply to wrong workspace
- Not recommended for production multi-tenant isolation

## EXAMPLE: Conditional File Generation

**Category:** generate  |  **Complexity:** advanced  |  Tags: generate, conditional, environment, disable

Generate files conditionally based on environment or configuration

```hcl
locals {
  env_config   = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  environment  = local.env_config.locals.environment
  is_prod      = local.environment == "production"
}

# Only generate monitoring in production
generate "monitoring" {
  path      = "monitoring.tf"
  if_exists = "overwrite_terragrunt"
  disable   = !local.is_prod
  contents  = <<EOF
resource "aws_cloudwatch_metric_alarm" "high_cpu" {
  alarm_name          = "${local.environment}-high-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = "120"
  statistic           = "Average"
  threshold           = "80"
  alarm_description   = "CPU utilization exceeded 80%"
}
EOF
}

# Generate different configs per environment
generate "logging" {
  path      = "logging.tf"
  if_exists = "overwrite_terragrunt"
  contents  = local.is_prod ? <<EOF
# Production logging with long retention
resource "aws_cloudwatch_log_group" "app" {
  name              = "/app/${local.environment}"
  retention_in_days = 365
}
EOF
: <<EOF
# Non-production logging with short retention
resource "aws_cloudwatch_log_group" "app" {
  name              = "/app/${local.environment}"
  retention_in_days = 7
}
EOF
}
```

**Use cases:** Add monitoring only to production; Use different configurations per environment; Disable expensive resources in development

**Pitfalls:**
- Complex conditionals become hard to maintain
- Environment drift can cause deployment issues
- Test conditional logic in all environments

## EXAMPLE: Dynamic Backend Generation

**Category:** generate  |  **Complexity:** intermediate  |  Tags: generate, backend, s3, state, dynamodb

Generate backend configuration dynamically based on environment

```hcl
# Generate backend configuration for S3
generate "backend" {
  path      = "backend.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
terraform {
  backend "s3" {
    bucket         = "${local.backend_bucket}"
    key            = "${path_relative_to_include()}/terraform.tfstate"
    region         = "${local.aws_region}"
    encrypt        = true
    dynamodb_table = "${local.lock_table}"
  }
}
EOF
}

locals {
  # Load environment-specific config
  env_config = read_terragrunt_config(find_in_parent_folders("env.hcl"))

  backend_bucket = local.env_config.locals.backend_bucket
  aws_region     = local.env_config.locals.aws_region
  lock_table     = local.env_config.locals.lock_table
}
```

**Use cases:** Centralize backend configuration; Use different state buckets per environment; Dynamically compute state file paths

**Pitfalls:**
- Changing backend config requires state migration
- Ensure bucket and table exist before first run
- Don't hardcode credentials in generated files

## EXAMPLE: Dynamic Provider Generation

**Category:** generate  |  **Complexity:** intermediate  |  Tags: generate, provider, aws, assume-role, tags

Generate provider configuration with assume role and region

```hcl
# Generate AWS provider with assume role
generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
provider "aws" {
  region = "${local.aws_region}"

  assume_role {
    role_arn     = "arn:aws:iam::${local.account_id}:role/TerraformRole"
    session_name = "terragrunt-${local.environment}"
  }

  default_tags {
    tags = {
      Environment = "${local.environment}"
      ManagedBy   = "Terragrunt"
      Project     = "${local.project_name}"
    }
  }
}
EOF
}

locals {
  env_config   = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  account_vars = read_terragrunt_config(find_in_parent_folders("account.hcl"))

  aws_region   = local.env_config.locals.aws_region
  environment  = local.env_config.locals.environment
  account_id   = local.account_vars.locals.account_id
  project_name = "my-infrastructure"
}
```

**Use cases:** Standardize provider configuration across modules; Implement cross-account access with assume role; Apply consistent default tags to all resources

**Pitfalls:**
- Ensure IAM roles have proper trust policies
- Session names have length limits (64 chars)
- Default tags don't apply to all resource types

## EXAMPLE: Version Constraints Generation

**Category:** generate  |  **Complexity:** basic  |  Tags: generate, versions, terraform, providers, tfenv

Generate required providers and terraform version constraints

```hcl
# Generate version constraints
generate "versions" {
  path      = "versions.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
terraform {
  required_version = ">= 1.5.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }
}
EOF
}

# Optional: Generate .terraform-version file for tfenv
generate "tfversion" {
  path      = ".terraform-version"
  if_exists = "overwrite_terragrunt"
  contents  = "1.5.7"
}
```

**Use cases:** Enforce consistent Terraform versions across team; Pin provider versions for reproducibility; Support tfenv/tgenv version management

**Pitfalls:**
- Too strict constraints block security patches
- Too loose constraints can break builds
- Coordinate version changes across team

## EXAMPLE: Error Handling Hooks

**Category:** hooks  |  **Complexity:** advanced  |  Tags: hooks, error-handling, cleanup, run_on_error, alerting

Hooks that run on errors for cleanup and alerting

```hcl
terraform {
  # Cleanup hook that runs even on failure
  after_hook "cleanup_temp_files" {
    commands     = ["apply", "plan", "destroy"]
    execute      = ["rm", "-rf", ".terraform-temp"]
    run_on_error = true
  }

  # Error notification hook - runs only when command fails
  after_hook "notify_on_failure" {
    commands     = ["apply"]
    execute      = ["./scripts/alert-failure.sh", "${path_relative_to_include()}"]
    run_on_error = true  # Only runs on error, no need to check exit code
  }

  # State backup before risky operations
  before_hook "backup_state" {
    commands     = ["apply", "destroy"]
    execute      = ["./scripts/backup-state.sh", get_terragrunt_dir()]
  }
}
```

**Use cases:** Clean up temporary resources on failure; Alert on-call teams when deployments fail; Create state backups before risky operations

**Pitfalls:**
- Error hooks themselves can fail - keep them simple
- Don't create infinite loops with error notifications
- State backup hooks should handle large state files efficiently

## EXAMPLE: Multi-Command Hook Pipeline

**Category:** hooks  |  **Complexity:** advanced  |  Tags: hooks, pipeline, security, formatting, documentation, cost

Complex hook with multiple commands for different operations

```hcl
terraform {
  # Format check before any terraform operation
  before_hook "terraform_fmt" {
    commands     = ["apply", "plan", "validate"]
    execute      = ["terraform", "fmt", "-check", "-recursive"]
  }

  # Security scan before apply
  before_hook "security_scan" {
    commands     = ["apply"]
    execute      = ["tfsec", "."]
    working_dir  = get_terragrunt_dir()
  }

  # Cost estimation before apply
  before_hook "cost_estimate" {
    commands     = ["apply"]
    execute      = ["infracost", "breakdown", "--path", "."]
    working_dir  = get_terragrunt_dir()
  }

  # Documentation generation after successful apply
  after_hook "generate_docs" {
    commands     = ["apply"]
    execute      = ["terraform-docs", "markdown", ".", "--output-file", "README.md"]
    working_dir  = get_terragrunt_dir()
    run_on_error = false
  }
}
```

**Use cases:** Enforce code formatting standards; Run security scans before deployments; Generate cost estimates for review; Auto-generate documentation

**Pitfalls:**
- Too many hooks can significantly slow down operations
- External tools must be available in execution environment
- Consider caching for expensive operations like security scans

## EXAMPLE: Post-Apply Notification Hook

**Category:** hooks  |  **Complexity:** intermediate  |  Tags: hooks, notification, after_hook, slack, apply

Send notifications after successful deployments

```hcl
terraform {
  after_hook "notify_slack" {
    commands     = ["apply"]
    execute      = [
      "curl", "-X", "POST",
      "-H", "Content-Type: application/json",
      "-d", "{\"text\": \"Deployment completed for ${path_relative_to_include()}\"}",
      "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
    ]
    run_on_error = false
  }

  after_hook "update_deployment_log" {
    commands     = ["apply"]
    execute      = ["./scripts/log-deployment.sh", path_relative_to_include()]
    run_on_error = true
  }
}
```

**Use cases:** Notify team members of successful deployments; Update deployment tracking systems; Trigger downstream processes after infrastructure changes

**Pitfalls:**
- Don't include sensitive data in notifications
- Webhook URLs should be stored securely (use environment variables)
- Notification failures shouldn't block deployments

## EXAMPLE: Pre-Apply Validation Hook

**Category:** hooks  |  **Complexity:** intermediate  |  Tags: hooks, validation, before_hook, apply, plan

Run validation scripts before apply to catch issues early

```hcl
terraform {
  before_hook "validate_inputs" {
    commands     = ["apply", "plan"]
    execute      = ["./scripts/validate-inputs.sh"]
    working_dir  = get_repo_root()
  }

  before_hook "check_dependencies" {
    commands     = ["apply"]
    execute      = ["terraform", "validate"]
  }
}
```

**Use cases:** Validate input variables before expensive operations; Run custom compliance checks before apply; Ensure prerequisites are met before deployment

**Pitfalls:**
- Long-running validations can frustrate developers
- Validation scripts must be idempotent
- Ensure scripts are available in CI/CD environments
