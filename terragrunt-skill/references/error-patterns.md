# Terragrunt Error Diagnosis Playbook

> **Provenance, measured 2026-08-20 rather than asserted.** 66 of the 69 entries at import were
> harvested at import from omattsson/terragrunt-mcp-server — a repo whose last commit is
> 2026-02-22, five weeks before Terragrunt v1.0.0 existed. Three were written here
> (both Azure entries, and `ParentFileNotFoundError`, which was reproduced on 1.1.3).
> Thirty-seven have since been rewritten against the 1.1.3 binary and a dated docs snapshot,
> and nine generic HCL entries were folded into one.
>
> **What that means for you.** Every entry names likely causes. **Only 49 carry a fix**, and an
> entry with no `**Solutions:**` section has none to give — say so rather than improvising one.
> An entry carrying a "Verified against terragrunt 1.1.3" line was checked against the binary
> on that date; the rest were not, and may describe a pre-1.0 world. Flag and avoid pre-1.0
> idioms wherever they appear.
>
> Refining an entry means: reproduce the error, paste what the tool actually printed, and give
> the command that fixes it on a current build. Not paraphrase the cause more fluently.

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
- **configuration** (31): HCL that will not parse or evaluate, the seven `include` entries, the five `generate` entries, the five `locals` entries, the seven hook entries, No Terraform configuration files found, Missing required input variable, Remote state configuration missing, Invalid terraform source, Working directory error, ParentFileNotFoundError on a file that sits beside the config
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

`init` fails because the GCS bucket named in `remote_state` is not there.

**Likely causes:**
- Bucket name is wrong, or it lives in a different project.
- The active project is not the one you think. The `google` provider has **no required
  `project` argument**, so an unset value falls through to `GOOGLE_PROJECT`, then ADC, then
  whatever `gcloud config set project` last selected. See references/hcl-blocks.md.
- **You expected Terragrunt to create it.** `--backend-bootstrap` defaults to `false`.
  `gcs` is one of the two backends that *can* be bootstrapped, but not by default.

**Solutions:**

```bash
# Which project is actually active, and does the bucket exist in it?
gcloud config get-value project
gcloud storage buckets describe gs://<bucket-name>

# Create it through Terragrunt rather than by hand:
terragrunt backend bootstrap
```

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: S3 bucket does not exist
**Category:** backend

`init` fails because the S3 bucket named in `remote_state` is not there.

**Likely causes:**
- Bucket name or region is wrong, or the bucket was deleted.
- **You expected Terragrunt to create it. By default it does not.**
  `--backend-bootstrap` defaults to **`false`**, so Terragrunt creates no backend resources
  and OpenTofu/Terraform's own `init` fails with "bucket not found". This is the cause that
  looks like the other three and is not.
- `disable_init = true` in the `remote_state` block. Then nothing is created regardless of
  `--backend-bootstrap`, and init still tries to reach the bucket.

**Solutions:**

```bash
# Does it exist at all, and are you the principal you think you are?
aws s3api head-bucket --bucket <bucket-name>
aws sts get-caller-identity

# Let Terragrunt create it -- explicitly, once:
terragrunt backend bootstrap

# ...or per-run, which also verifies the config of a bucket that already exists:
terragrunt run --backend-bootstrap -- init
```

Only the **`s3` and `gcs`** backends support automatic creation. `azurerm` does not — see
"Azure storage account not found".

For S3 specifically, Terragrunt will also *update* an existing bucket to match the
`remote_state` block (versioning, for example), which is why bootstrap is worth running against
a bucket that already exists.

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: After apply hook failed
**Category:** configuration

An `after_hook` returned non-zero. The apply already happened — the infrastructure change is
done and only the hook failed.

> **Hooks are nested inside the `terraform` block, not top level**, and `execute` takes a
> **list**, not a string: `execute = ["echo", "Foo"]` runs `echo Foo`. A string is the most
> common shape error and it does not read like one.

**Likely causes:**
- The hook assumes the apply succeeded. By default an `after_hook` **does not run** when the
  command failed; if you set `run_on_error = true` to change that, the hook must cope with a
  failed apply rather than assume outputs exist.
- It reads `terragrunt output` for a value the apply did not create.
- It writes somewhere the CI runner cannot.

**Solutions:**

```hcl
terraform {
  after_hook "notify" {
    commands     = ["apply"]
    execute      = ["${get_terragrunt_dir()}/scripts/notify.sh"]
    run_on_error = true          # then handle failure inside the script
  }
}
```

Inside the script, `TG_CTX_COMMAND` tells you which subcommand ran and `TG_CTX_HOOK_NAME`
which hook you are in — see "Hook environment variable missing".

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Before init hook failed
**Category:** configuration

A `before_hook` returned non-zero, so Terragrunt stopped before running OpenTofu/Terraform.

> **Hooks are nested inside the `terraform` block, not top level**, and `execute` takes a
> **list**, not a string: `execute = ["echo", "Foo"]` runs `echo Foo`. A string is the most
> common shape error and it does not read like one.

**Likely causes:**
- The script is not executable, or is not on `PATH`. `execute = ["hook.sh"]` needs `hook.sh`
  resolvable **from the hook's working directory**, which is not necessarily where you think —
  see "Hook working directory error".
- `commands` does not list the subcommand you are running, so a hook you believed was tested
  never ran until now.
- The hook depends on something `init` was going to produce. A `before_hook` on `init` runs
  before the module is downloaded.

**Solutions:**

```hcl
terraform {
  before_hook "check" {
    commands = ["init", "plan", "apply"]   # a list of subcommands, not "all"
    execute  = ["${get_terragrunt_dir()}/scripts/check.sh"]
  }
}
```

```bash
# Run the hook exactly as Terragrunt would, from the module directory:
terragrunt run -- init
```

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Circular dependency in locals
**Category:** configuration

Two locals referencing each other, so neither can be evaluated.

**The error does not contain the word "circular", which is why grepping for it fails.**
Terragrunt evaluates `locals` in passes, and reports an unresolvable reference as one that is
not ready. Reproduced on 1.1.3 with `a = local.b` and `b = local.a`:

```
Error: Can't evaluate expression
  on terragrunt.hcl line 5, in locals:
   5:   b = local.a
The local reference 'a' is not evaluated. Either it is not ready yet in the current pass, or
there was an error evaluating it in an earlier stage.
```

**Read "is not evaluated" as "cannot be evaluated from here".** The same message appears when
the reference is not circular at all but simply failed earlier — see "Local evaluation error".

**Likely causes:**
- A genuine two-way reference between locals.
- A local referring to itself, often after a rename.
- A chain through `read_terragrunt_config` that comes back to the file it started in.

**Solutions:**

```bash
# Which local is unresolvable? render evaluates everything and stops at the first one:
terragrunt render
```

Break the loop by computing the shared part once and having both locals read it, or by moving it
into a file both read with `read_terragrunt_config`.

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Circular include detected
**Category:** configuration

An include chain that Terragrunt refuses to follow. In practice this is almost never a true
cycle — it is a **chain**, and Terragrunt allows none.

> **Terragrunt supports ONE level of `include`.** If a config you include has its own `include`
> block, the run fails. Reproduced on 1.1.3:
>
> ```
> a/b/terragrunt.hcl includes a/mid.hcl, which itself includes root.hcl.
> Only one level of includes is allowed.
> ```
>
> Tracked upstream as gruntwork-io/terragrunt#1566. Until it lands, a child must include every
> file it needs **directly** — `include` blocks are additive and merge by label, so several
> siblings are fine; a chain is not.

**Likely causes:**
- An `_envcommon`-style file that itself includes the root, included by a unit. Two hops.
- A genuine loop: A includes B, B includes A.
- Refactoring a shared file into a "base" that includes another base.

**Solutions:**

```hcl
# Flatten it. Both files, directly, in the unit:
include "root" {
  path = find_in_parent_folders("root.hcl")
}

include "envcommon" {
  path           = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/service.hcl"
  merge_strategy = "deep"
}
```

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: HCL that will not parse or evaluate

**Category:** configuration

Generic HCL failures — a syntax error, an unknown attribute, a duplicate block, a bad
interpolation, a type mismatch, a function called wrongly. **Nine separate entries used to sit
here, one per wording. They were folded into this one on 2026-08-20** because none of them said
anything Terragrunt-specific: the same text would apply to any HCL, the causes restated the
titles, and `terragrunt hcl validate` already reports every one of them with a file, a line and
a fix — which is more than any of those entries offered.

**Likely causes:**
- A brace, quote or bracket that does not close — including a single-line block left open.
- An attribute the block does not define, or the same block declared twice.
- A `${...}` that references something not in scope at that evaluation stage.
- A value of the wrong type: `yamldecode` preserves the source type, so `"true"` is a string.
- A function called with the wrong arity or argument types.

**Solutions:**

**Run the validator. It is better than this file at this class of error.**

```bash
terragrunt hcl validate            # every config under the current directory
terragrunt hcl fmt --check --diff  # formatting, separately
```

It points at the line. A real one, from 1.1.3:

```
│ Error: Invalid single-argument block definition
│
│   on terragrunt.hcl line 1, in terraform:
│    1: terraform { source = "./mod"
│    2: inputs = { a = }
│
│ An argument definition on the same line as its containing block creates a
│ single-line block definition, which must also be closed on the same line.
```

**Two Terragrunt-specific traps that look like generic HCL errors and are not:**

- **`values.*` is unbound outside a generated unit.** Validating a `catalog/` unit in place
  reports `Error: Unknown variable` for every `values.` reference. That is not a defect —
  run `terragrunt stack generate` and validate the materialised units instead. See
  `references/architecture-patterns.md`, `## PATTERN: two accounts, many regions`.
- **A `${...}` inside a `generate` heredoc is evaluated by Terragrunt**, not passed through.
  Escape it as `$${...}` to emit a literal one. See "Generate template error".

If the validator passes and the config still misbehaves, the problem is evaluation rather than
syntax — see "Local evaluation error" and "Include merge conflict", and read the resolved
config with `terragrunt render`.

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Generate if_exists strategy error
**Category:** configuration

`if_exists` was given a value that is not one of the four Terragrunt accepts.

| value | what it does |
|---|---|
| `overwrite` | replace the file whatever wrote it |
| `overwrite_terragrunt` | replace it **only if Terragrunt generated it**; otherwise error |
| `skip` | leave the existing file alone |
| `error` | exit with an error |

`overwrite_terragrunt` is the one to reach for by default: it refuses to clobber a file a human
wrote, which is the failure mode `overwrite` has.

**There is a second, separate attribute that is easy to confuse with it.** `if_disabled`
controls what happens to an already-generated file when `disable = true`, and it takes a
*different* set of values: `remove`, `remove_terragrunt`, `skip` (default `skip`).

**Likely causes:**
- A plausible-sounding value that does not exist — `replace`, `force`, `always`, `never`.
- `if_disabled` values used on `if_exists` or the reverse.

**Solutions:**

```hcl
generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
provider "aws" {
  region = "eu-central-1"
}
EOF
}
```

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Generate invalid path
**Category:** configuration

`path` does not resolve to somewhere Terragrunt can write.

**`path` is relative to the OpenTofu/Terraform working directory, not to your config.** When
`source` is remote that working directory is a temporary copy under `.terragrunt-cache`, so a
path reaching outside it — `../shared/provider.tf` — points somewhere that will not survive,
or does not exist.

**Likely causes:**
- An absolute path, or one climbing out of the module directory with `..`.
- A path with a directory component that does not exist. Terragrunt writes a file; it does not
  create the tree above it.
- Expecting the file to appear in the repo. It appears in the working directory, which for a
  remote `source` is under `.terragrunt-cache`.

**Solutions:**

```hcl
generate "backend" {
  path      = "backend.tf"      # a bare filename is almost always right
  if_exists = "overwrite_terragrunt"
  contents  = "..."
}
```

```bash
# Where did it actually go?
terragrunt render
find . -path '*.terragrunt-cache*' -name 'backend.tf'
```

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Generate permission denied
**Category:** configuration

Terragrunt could not write the generated file.

**Likely causes:**
- The working directory is read-only. On a container or a hardened CI runner the checkout is
  sometimes mounted read-only, and `generate` is the first thing that needs to write.
- `.terragrunt-cache` owned by another user — the classic case is a run under `sudo` leaving
  root-owned files behind for the next non-root run.
- With the **`mutable-generate` experiment** (v1.1.3+) the generated file is a **read-only link
  into the CAS** rather than an ordinary file. Anything expecting to edit it in place fails
  here. `mutable = true` on that block gives it a writable file of its own.

**Solutions:**

```bash
# Who owns the cache, and can you write it?
ls -ld .terragrunt-cache
find . -name .terragrunt-cache -user root

# Move the cache somewhere writable rather than fighting the checkout:
TG_DOWNLOAD_DIR=/tmp/tg-cache terragrunt run -- plan
```

`mutable` exists on three different blocks with three different meanings — check which one you
are reading in `references/hcl-blocks.md` before setting it.

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Generate template error
**Category:** configuration

`contents` failed to evaluate, usually inside a heredoc.

**The trap is that a heredoc is still interpolated.** `${...}` inside `contents` is evaluated
by *Terragrunt*, so any Terraform interpolation you meant to pass through to the generated file
is consumed before Terraform ever sees it. Escape it as `$${...}` to emit a literal `${...}`.

**Likely causes:**
- A Terraform expression in the generated file being eaten by Terragrunt's own interpolation.
- A reference to a `local` or a function that is not resolvable at generate time.
- An unterminated heredoc, or trailing whitespace after the opening `<<EOF`.

**Solutions:**

```hcl
generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
provider "aws" {
  region = "${local.region}"        # evaluated by Terragrunt -- intended
  assume_role {
    role_arn = "$${var.role_arn}"   # emitted literally for Terraform -- escaped
  }
}
EOF
}
```

```bash
# See exactly what would be written, with everything resolved:
terragrunt render
```

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Generated file already exists
**Category:** configuration

A file is already at `path` and `if_exists` told Terragrunt to stop rather than replace it.

**This is `if_exists` working, not failing.** With `error` it stops always; with
`overwrite_terragrunt` it stops only when the existing file was **not** generated by Terragrunt
— which means a human wrote it, or a previous run wrote it with `disable_signature = true` and
Terragrunt can no longer recognise its own output.

**Likely causes:**
- A hand-written `provider.tf` or `backend.tf` in a module that a `generate` block also targets.
- `disable_signature = true` on an earlier run, so the signature Terragrunt looks for is gone.
- A stale file left in `.terragrunt-cache` from a run that was interrupted.

**Solutions:**

```bash
# Which file, and did Terragrunt write it? Its signature comment is the tell:
head -3 <module-dir>/provider.tf
```

```hcl
# Then pick deliberately:
if_exists = "overwrite_terragrunt"   # replace only Terragrunt's own output
if_exists = "skip"                   # the hand-written file wins
```

Do not reach for `overwrite` to make the message go away — that is how a hand-written provider
config disappears without anyone noticing.

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Hook command failed
**Category:** configuration

The command in `execute` exited non-zero. Terragrunt reports the exit status; the reason is in
the hook's own output.

> **Hooks are nested inside the `terraform` block, not top level**, and `execute` takes a
> **list**, not a string: `execute = ["echo", "Foo"]` runs `echo Foo`. A string is the most
> common shape error and it does not read like one.

**Likely causes:**
- `execute` given a shell string rather than a list. `execute = ["ls -la"]` looks for a binary
  literally named `ls -la`. Use `["ls", "-la"]`, or `["bash", "-c", "ls -la"]` when you
  genuinely need a shell.
- A relative path in `execute` resolved from the module directory rather than the config
  directory.
- The hook's output is hidden because `suppress_stdout = true` is set on it.

**Solutions:**

```hcl
terraform {
  before_hook "shell" {
    commands = ["plan"]
    execute  = ["bash", "-c", "set -euo pipefail; ./scripts/preflight.sh"]
  }
}
```

If you cannot see why it failed, remove `suppress_stdout` first — that attribute is the reason
a failing hook can look silent.

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Hook environment variable missing
**Category:** configuration

A hook script expected an environment variable that is not set.

**Terragrunt sets three context variables for every hook**, and they are the ones worth using
rather than passing arguments:

| variable | is |
|---|---|
| `TG_CTX_TF_PATH` | the `tofu`/`terraform` binary being wrapped |
| `TG_CTX_COMMAND` | the subcommand that triggered the hook |
| `TG_CTX_HOOK_NAME` | the hook's own label |

Three more — `TG_CTX_HOOK_TYPE`, `TG_CTX_SOURCE`, `TG_CTX_TERRAGRUNT_DIR` — require the
**`hook-context-env` experiment**. They are absent without it, which is the usual reason a
script reading `TG_CTX_TERRAGRUNT_DIR` finds nothing.

**Likely causes:**
- Reading one of the three experiment-gated variables without enabling the experiment.
- Expecting the parent shell's environment. A hook inherits Terragrunt's environment, so
  anything set only in your interactive shell is absent in CI.
- A `TF_VAR_*` set by a `before_hook` for a later hook — each `execute` is its own process and
  exported variables do not survive between them.

**Solutions:**

```bash
# Enable the extra three, if you want them:
terragrunt run --experiment hook-context-env -- apply
```

```hcl
# Otherwise pass what the script needs explicitly rather than relying on inheritance:
execute = ["bash", "-c", "MY_DIR='${get_terragrunt_dir()}' ./scripts/x.sh"]
```

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Hook execution timeout
**Category:** configuration

**Terragrunt has no hook timeout.** There is no `hook_timeout` attribute, no flag, and no
default limit — a hook that hangs hangs the run, and Terragrunt waits. If something reported a
"hook execution timeout", it came from your own script, from CI, or from the tool the hook
called, not from Terragrunt.

Recorded here because the name is what people search for, and the answer is that the mechanism
they are looking for does not exist.

**Likely causes:**
- The CI job's own step timeout fired while a hook was waiting.
- A hook waiting on input. There is no TTY in CI, so a prompt waits forever. Pass
  `--non-interactive`, and make the hook non-interactive too.
- A hook holding a lock or a network call with no timeout of its own.

**Solutions:**

```hcl
# Put the bound in the hook, since Terragrunt will not:
execute = ["timeout", "300", "${get_terragrunt_dir()}/scripts/slow.sh"]
```

```bash
# And make sure nothing is waiting for a prompt:
terragrunt run --non-interactive -- apply
```

Verified against terragrunt 1.1.3 and the docs of 2026-08-20: no hook timeout attribute exists.

## ERROR: Hook log suppression error
**Category:** configuration

Hook output you expected is missing. Usually not an error at all — `suppress_stdout` is doing
exactly what it says.

`suppress_stdout = true` exists so a script parsing OpenTofu/Terraform's output is not
disrupted by a hook writing to the same stream. It suppresses the hook's **stdout**. A hook
that fails silently is nearly always this attribute plus a script that writes its diagnostics
to stdout rather than stderr.

**Likely causes:**
- `suppress_stdout = true` on the hook you are trying to debug.
- The hook writes to stdout when it should write to stderr, so suppression takes the errors too.
- `--log-level` set low enough to hide Terragrunt's own hook lines.

**Solutions:**

```hcl
# Drop the suppression while debugging, then put it back:
before_hook "noisy" {
  commands = ["plan"]
  execute  = ["./scripts/x.sh"]
  # suppress_stdout = true
}
```

```bash
terragrunt run --log-level debug -- plan
```

Write hook diagnostics to stderr (`echo "..." >&2`) so they survive suppression.

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Hook working directory error
**Category:** configuration

The hook ran somewhere other than where its relative paths expect.

**The default working directory is not the same for every hook, and this is the surprise.**
Hooks run from the **OpenTofu/Terraform module directory** — except hooks on `read-config` and
`init-from-module`, which run from the **Terragrunt configuration directory** (where
`terragrunt.hcl` lives). So the same `execute = ["./scripts/x.sh"]` works in one hook and not
in another, in the same file.

**Likely causes:**
- A relative script path, with the hook attached to a command whose default directory differs
  from the one you tested.
- The module directory is a **temporary** `.terragrunt-cache` copy when `source` is remote, so
  paths relative to your repo do not exist there at all.
- `working_dir` set to a path that does not exist yet at hook time.

**Solutions:**

```hcl
terraform {
  before_hook "preflight" {
    commands = ["plan", "apply"]
    # Anchor to the config directory rather than relying on the default:
    execute  = ["${get_terragrunt_dir()}/scripts/preflight.sh"]
    # or set it explicitly:
    working_dir = get_terragrunt_dir()
  }
}
```

`get_terragrunt_dir()` is the reliable anchor: it is the directory of the config file being
processed, whatever the hook's default happens to be.

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Include dependency resolution error
**Category:** configuration

A `dependency` block inherited through an include does not resolve.

**Likely causes:**
- The `config_path` in the inherited `dependency` is relative, and relative paths in an included
  config resolve from the **including unit**, not from the file that declared them. A path that
  worked for one unit breaks for a unit at a different depth.
- The dependency's outputs do not exist yet because that unit has never been applied. Use
  `mock_outputs` with `mock_outputs_allowed_terraform_commands` so `plan` works before the first
  apply.
- A `dependencies` block (plural) inherited from several includes, whose paths concatenate under
  shallow merge — see "Include merge conflict".

**Solutions:**

```hcl
# In the shared file, anchor rather than count directories:
dependency "vpc" {
  config_path = "${dirname(find_in_parent_folders("root.hcl"))}/network/vpc"

  mock_outputs = {
    vpc_id = "vpc-00000000"
  }
  mock_outputs_allowed_terraform_commands = ["plan", "validate"]
}
```

```bash
terragrunt render          # what config_path did it actually resolve to?
terragrunt dag graph       # and does the edge exist where you think?
```

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Include expose configuration conflict
**Category:** configuration

A reference to `include.<label>.…` that does not resolve.

**`expose` is off by default, and nothing about the failure says so.** Without
`expose = true` on the include block, the included config's `locals` and `inputs` are not
reachable at all — and a parent's `locals` are **never** available as bare `local.x` in the
child, exposed or not.

Reproduced on 1.1.3, a child referencing `local.region` for a local defined in the included
root:

```
Error: Unsupported attribute
  on child/terragrunt.hcl line 3:
   3: inputs = { r = local.region }
```

Adding `expose = true` and reading `include.root.locals.region` resolves it.

**Likely causes:**
- `expose` not set.
- The label in the reference not matching the block's label — `include.root` requires
  `include "root"`.
- Expecting inheritance of `locals`. They do not inherit. Only `expose` makes them reachable,
  and under a different name.

**Solutions:**

```hcl
include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

locals {
  region = include.root.locals.region     # NOT local.region
}
```

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Include file not found
**Category:** configuration

The `path` in an `include` block does not resolve to a file. Reproduced on 1.1.3:

```
Include configuration not found: /repo/live/nope.hcl (referenced from: /repo/live/terragrunt.hcl)
```

The message names both files, which is the fastest way to see whether the path or the
referencing location is wrong.

**Likely causes:**
- `find_in_parent_folders` pointed at a **sibling**. It searches strictly upward and never looks
  in the referencing file's own directory — see the `ParentFileNotFoundError` entry.
- A relative `path` written relative to the repo root rather than to the unit.
- The file exists but is named `terragrunt.hcl` while the include asks for `root.hcl`, or the
  reverse. 1.x convention is `root.hcl`.

**Solutions:**

```hcl
include "root" {
  path = find_in_parent_folders("root.hcl")     # an ancestor
}

include "envcommon" {
  path = "${get_terragrunt_dir()}/common.hcl"   # a sibling
}
```

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Include file parse error
**Category:** configuration

The included file was found and is not valid HCL, or is valid HCL that Terragrunt cannot use as
a config.

**Likely causes:**
- A syntax error in the *included* file. The failure surfaces in the unit, so the file named in
  the error is not always the file to fix — read the location line.
- A `.hcl` file that is a values file or a fragment, not a Terragrunt config.
- BOM or CRLF line endings from a Windows editor.

**Solutions:**

```bash
# Validate the included file on its own, before the unit that includes it:
terragrunt hcl validate --working-dir <dir-containing-the-included-file>
terragrunt hcl fmt --check --diff
```

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Include merge conflict
**Category:** configuration

Two includes, or an include and the unit, define the same thing and the result is not what you
expected.

**The merge strategy is `shallow` unless you say otherwise**, and shallow means *replace*:

| `merge_strategy` | effect |
|---|---|
| `shallow` (default) | attributes and blocks replaced wholesale by the child |
| `deep` | maps and nested blocks merged key by key |
| `no_merge` | the included config is parsed but not merged at all |

**The exception that catches people:** under a shallow merge everything is replaced **except
`dependencies` blocks** (the plural block, not `dependency`). Those are deep-merged — the lists
of paths from every included config are concatenated rather than overridden.

**Likely causes:**
- A child setting one key of `inputs` and silently discarding the rest, because shallow replaces
  the whole map. `merge_strategy = "deep"` is what you wanted.
- Two `include` blocks with the same label. Each needs a distinct one; they merge by label.
- Expecting `dependencies` to be replaced, and getting the union.

**Solutions:**

```hcl
include "envcommon" {
  path           = "${dirname(find_in_parent_folders("root.hcl"))}/_envcommon/app.hcl"
  merge_strategy = "deep"
}
```

```bash
# The merged result, with everything resolved. Read this rather than reasoning about it:
terragrunt render
```

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Include path traversal limit
**Category:** configuration

The same one-level rule as "Circular include detected", reached by climbing rather than looping.

> **Terragrunt supports ONE level of `include`.** If a config you include has its own `include`
> block, the run fails. Reproduced on 1.1.3:
>
> ```
> a/b/terragrunt.hcl includes a/mid.hcl, which itself includes root.hcl.
> Only one level of includes is allowed.
> ```
>
> Tracked upstream as gruntwork-io/terragrunt#1566. Until it lands, a child must include every
> file it needs **directly** — `include` blocks are additive and merge by label, so several
> siblings are fine; a chain is not.

**Likely causes:**
- A deep tree where each level includes the one above it, so a leaf is three or four hops from
  the root config.
- An include `path` built with several `..` segments that resolves outside the repo.

**Solutions:**

```bash
# What is including what? render resolves the whole graph and fails loudly if it cannot:
terragrunt render
```

Anchor paths to a marker file rather than counting directories — `find_in_parent_folders("root.hcl")`
holds when a unit moves; `../../../root.hcl` does not.

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Invalid terraform source
**Category:** configuration

The terraform source URL format is invalid

**Likely causes:**
- Malformed URL or path
- Unsupported source type
- Missing required URL components

## ERROR: Local evaluation error
**Category:** configuration

A `locals` expression threw while being evaluated.

Terragrunt evaluates locals in passes and reports a local it could not finish with the same
wording it uses for a circular reference — `The local reference 'x' is not evaluated. Either it
is not ready yet in the current pass, or there was an error evaluating it in an earlier stage.`
**"Or there was an error" is the half people skip.** If the reference is not circular, something
it calls failed.

**Likely causes:**
- `read_terragrunt_config` pointed at a file that does not exist, or that fails to parse. The
  failure is attributed to the local, not to the file.
- `file()` or `yamldecode()` on a missing or malformed file.
- `get_env("X")` with no default, where `X` is unset.
- A function that is not available at this evaluation stage — `dependency` outputs are not
  resolvable inside `locals`.

**Solutions:**

```hcl
locals {
  # Give the reads a default so a missing file is visible rather than fatal:
  env_vars = read_terragrunt_config(find_in_parent_folders("env.hcl", "none.hcl"), {})
  region   = get_env("AWS_REGION", "eu-central-1")
}
```

```bash
terragrunt render --log-level debug
```

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Local type error
**Category:** configuration

A local holds a different type from the one the expression using it assumes.

**Likely causes:**
- A value read from YAML or JSON arriving as a string when a number or bool was expected —
  `yamldecode` preserves the source type, and `"true"` is not `true`.
- A list where a map is expected, usually after a `for` expression.
- `read_terragrunt_config` returning a whole config object where a scalar was wanted: the value
  is under `.locals.<name>`, and the object itself is not a string.

**Solutions:**

```hcl
locals {
  raw     = yamldecode(file("${get_terragrunt_dir()}/config.yaml"))
  enabled = tobool(local.raw.enabled)     # be explicit rather than hoping
  count   = tonumber(local.raw.count)
}
```

```bash
# What type is it actually? render prints the resolved config:
terragrunt render
```

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Locals merge error
**Category:** configuration

An expectation that `locals` combine across files. **They do not merge, at all.**

`merge_strategy` on an `include` governs attributes and blocks such as `inputs`, `remote_state`
and `dependencies`. It does not give the child a merged `local.` namespace, and no strategy —
`shallow`, `deep` or `no_merge` — changes that. `expose = true` makes the included config
readable under `include.<label>.locals`, which is a separate namespace, not a merge.

**Likely causes:**
- Two `locals` blocks in the same file. That is a duplicate block, not a merge — put everything
  in one.
- Assuming `deep` merges locals. It does not.
- Building a value from both parent and child locals and expecting one name to resolve to both.

**Solutions:**

```hcl
include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

locals {
  # Do the combining yourself, explicitly:
  tags = merge(
    include.root.locals.common_tags,
    { Service = "checkout" },
  )
}
```

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

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

## ERROR: Undefined local reference
**Category:** configuration

`local.<name>` does not exist in this config.

**A parent's `locals` are NOT inherited.** This is the cause most of the time, and nothing in
the message hints at it. Including a config does not merge its `locals` into your `local.`
namespace. Reproduced on 1.1.3 — a child including a root that defines `locals { region = ... }`:

```
Error: Unsupported attribute
  on child/terragrunt.hcl line 3:
   3: inputs = { r = local.region }
```

Set `expose = true` on the include and read it as `include.<label>.locals.<name>`, which is a
different name from the one you were reaching for.

**Likely causes:**
- Expecting inheritance from an included config. See above.
- A typo, or a local defined inside a *different* `locals` block in an included file.
- Reading a value out of `read_terragrunt_config(...)` without the `.locals` hop:
  it is `local.account_vars.locals.account_id`, not `local.account_vars.account_id`.

**Solutions:**

```hcl
include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

locals {
  region       = include.root.locals.region                    # from the include
  account_vars = read_terragrunt_config(find_in_parent_folders("account.hcl"))
  account_id   = local.account_vars.locals.account_id          # note the .locals hop
}
```

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Working directory error
**Category:** configuration

Cannot access or change to working directory

**Likely causes:**
- Directory does not exist
- Insufficient permissions
- Path is not a directory

## ERROR: Circular dependency detected
**Category:** dependency

Two or more units depend on each other, directly or through a chain, so no valid run order
exists and `run --all` refuses to build a queue.

**Likely causes:**
- A `dependency` block in A pointing at B while B points back at A.
- An indirect cycle through a third unit — the usual case, and the one nobody spots by reading.
- A `dependencies` block added "to force ordering" that closed a loop the outputs did not need.

**Solutions:**

```bash
# Print the DAG and look at it. This is the command for this error:
terragrunt dag graph

# It emits DOT, so render it if the estate is large:
terragrunt dag graph | dot -Tsvg > dag.svg
```

`dag graph` is an alias for `list --format=dot --dag --dependencies --external`, so the same
picture is available from `list` if you want to filter it.

Break the cycle by removing the weaker edge — usually a `dependencies` entry that exists for
ordering rather than for an output. If both units genuinely need a value from the other, one of
them is two units.

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

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

The Git remote in `source` refused the credentials, or was given none.

**Likely causes:**
- **The URL scheme decides which credential is used, and they do not interchange.**
  `git::git@github.com:org/repo.git` uses SSH and needs a key with an agent;
  `git::https://github.com/org/repo.git` uses HTTPS and needs a token or a credential helper.
  A CI runner with a token and an SSH-form source will fail no matter how correct the token is.
- No SSH agent in the environment Terragrunt runs in — a common surprise inside a container or
  a hook, where the agent socket is not forwarded.
- The token is valid but lacks read access to that specific repository.

**Solutions:**

```bash
# Test the exact remote the source names, in the same environment Terragrunt runs in:
GIT_TERMINAL_PROMPT=0 git ls-remote git@github.com:org/modules.git

# SSH form, no agent? Confirm the key is loaded:
ssh-add -l && ssh -T git@github.com

# In CI, rewrite SSH to HTTPS-with-token once rather than editing every source:
git config --global url."https://oauth2:$TOKEN@github.com/".insteadOf "git@github.com:"
```

Never put a token in the `source` string — it lands in `.terragrunt-cache` and in logs. See
`references/cicd.md` for the OIDC route.

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Git ref not found
**Category:** dependency

The `?ref=` in the source names a tag, branch or commit the remote does not have.

**Likely causes:**
- A typo, or a tag that was deleted or moved. A *moved* tag is the nasty one: the ref resolves,
  but Terragrunt may still be holding the old contents in its cache.
- The ref exists on a fork or a private mirror, not on the remote the source names.
- A shallow or filtered clone in CI that did not fetch tags.

**Solutions:**

```bash
# Does the remote have it? No clone required:
git ls-remote --tags --heads git@github.com:org/modules.git | grep <ref>

# Tag moved, or you suspect a stale cache: discard the cached source and refetch.
terragrunt run --source-update -- init
```

Pin to an immutable ref — a tag you never move, or a commit SHA. A branch name in `?ref=` means
the module can change under a run that changed nothing.

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

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

A half-written or unreadable `.terragrunt-cache` makes a module fail to load, most often as a
checksum or "failed to open zip archive" error rather than anything naming the cache.

**There is no `terragrunt clear-cache` command.** It was removed in the 1.0 CLI redesign and
1.1.3 answers it with `unknown command: "clear-cache". Terragrunt no longer forwards unknown
commands by default.` The cache is scratch space on disk; you delete it yourself.

**Likely causes:**
- A run killed part-way through a download.
- Two concurrent runs staging the same provider. **Fixed in v1.1.3** — before it, the first
  run to finish could delete an archive the other was still unpacking. If you are below
  1.1.3 and see this on a parallel CI matrix, upgrading is the fix, not clearing the cache.
- Cache directory permissions, or a full disk.

**Solutions:**

```bash
# Look before you delete -- run --all can leave a lot of these:
find . -type d -name ".terragrunt-cache"

# Then remove them. Terragrunt recreates the cache as needed.
find . -type d -name ".terragrunt-cache" -prune -exec rm -rf {} +
```

Set `TG_DOWNLOAD_DIR` to move the cache somewhere outside the working tree if you would rather
not have these scattered through the repo.

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Module checksum mismatch
**Category:** dependency

The downloaded module does not hash to what was expected.

**Likely causes:**
- **Two runs racing on one machine.** Before **v1.1.3**, concurrent runs staged provider
  downloads at the same path, so the first to finish could delete an archive the other was
  still unpacking. It surfaces as a checksum error or `failed to open zip archive`. On a
  parallel CI matrix with a shared runner, upgrading is the fix — not clearing anything.
- A moved tag: the ref is the same, the contents are not.
- A lock file committed from a different platform, or a truncated download.

**Solutions:**

```bash
terragrunt --version          # below 1.1.3 with parallel runs? upgrade first

# Then discard the cached source and refetch:
terragrunt run --source-update -- init
```

If it persists on a single serial run, the module content genuinely changed under a fixed ref.
Re-pin to a commit SHA rather than a tag.

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Module not found
**Category:** dependency

Terragrunt cannot resolve the `source` in the `terraform` block.

**Likely causes:**
- **The `//` is missing.** In a Git source, a *double* slash separates the repository from the
  subdirectory inside it: `git::git@github.com:org/modules.git//vpc?ref=v1.4.0`. With a single
  slash the whole path is treated as the repo. This is the most common form of this error and
  it does not look like a syntax problem.
- A relative local path resolved from the wrong place. A local `source` resolves relative to
  the unit's own directory, not your shell's.
- The ref exists but the subdirectory does not at that ref — see "Module subdirectory not found".
- Terragrunt is serving a stale cached copy of the source.

**Solutions:**

```bash
# What did Terragrunt actually resolve? render shows the config after includes and functions:
terragrunt render

# Force a fresh download rather than the cached copy:
terragrunt run --source-update -- init

# Point every source somewhere else without editing any file (useful to test a local clone):
terragrunt run --source-map git::git@github.com:org/modules.git=/abs/path/to/local -- plan
```

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Module registry unavailable
**Category:** dependency

Cannot access Terraform module registry

**Likely causes:**
- Network connectivity issues
- Registry is down
- Firewall blocking registry access

## ERROR: Module subdirectory not found
**Category:** dependency

The source resolved to a repository, but the subdirectory after the `//` is not in it.

**A double slash is REQUIRED, not a mistake.** `//` is how a module source separates the
repository from the path inside it, and it is also what makes relative paths between modules in
that repo work. If you are here because something told you double slashes are the bug, that is
backwards — a *single* slash is the bug.

**Likely causes:**
- The path after `//` is wrong, or is relative to the repo root when you wrote it relative to
  something else.
- The directory moved between refs. `?ref=v1.4.0` and `?ref=v2.0.0` can have different layouts,
  and the error only appears when you bump the ref.
- A trailing slash or a leading `./` after the `//`.

**Solutions:**

```bash
# What did Terragrunt actually resolve the source to?
terragrunt render

# Check the layout at the exact ref you pinned. A shallow clone is enough:
git clone --depth 1 --branch <ref> git@github.com:org/modules.git /tmp/mod-check
ls /tmp/mod-check/<subdir>
```

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Module version not found
**Category:** dependency

No published version of a registry module satisfies the constraint.

**Likely causes:**
- The constraint is tighter than anything published, or names a version that was yanked.
- The module has no published versions at all — usually a namespace or provider typo in the
  `tfr://` address.
- **You used a `version` attribute without the experiment.** Resolving a `tfr://` module by
  constraint rather than by an exact version in the URL is the `version-attribute` experiment
  and needs **v1.1.1+** plus the flag. Without it the attribute is not available, and the
  version has to be pinned in the source URL itself.
- A bare `tfr:///` (three slashes) does not resolve to a fixed registry — see
  `references/hcl-blocks.md` under `## BLOCK: terraform`.

**Solutions:**

```bash
# What versions actually exist? The terraform-registry skill answers this offline:
tfreg inspect-module terraform-aws-modules/vpc/aws --fields versions

# Pin the version in the source URL, which needs no experiment:
#   source = "tfr:///terraform-aws-modules/vpc/aws?version=5.8.1"
```

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

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

OpenTofu/Terraform detects that the backend block no longer matches the one recorded in
`.terraform/terraform.tfstate`, and refuses to continue until told which way to resolve it.

**The two flags do opposite things and one of them loses state. Pick deliberately.**

- `-reconfigure` — **discard** the local backend record and start fresh against the new
  backend. Existing state in the OLD location stays where it is; the new location starts
  empty. Right when the old state was a mistake or is already gone.
- `-migrate-state` — **copy** the state from the old backend to the new one. Right when the
  state is real and you are moving it.

**Likely causes:**
- Bucket, container, key or region changed in `remote_state`.
- A `key` derived from `path_relative_to_include()` moved because a unit was renamed or a
  directory was restructured. This is the common one and it looks like a config change
  because it is.
- Switching a unit between `dynamodb_table` and `use_lockfile`.

**Solutions:**

```bash
# Moving real state to a new location:
terragrunt init -migrate-state

# Repointing at a new backend and abandoning the old record:
terragrunt init -reconfigure
```

For moving state **between units** rather than between backends, 1.x has a first-class
command that does not go through `init` at all:

```bash
terragrunt backend migrate <src-unit> <dst-unit>
# --force is required if the destination bucket is not versioned
```

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Error acquiring state lock
**Category:** state

Another process holds the lock, or a crashed one never released it.

**The remediation depends on which locking mechanism you are using, and there are two.**
Check the `remote_state` block before doing anything:

- `dynamodb_table = "..."` — the classic S3 + DynamoDB lock table. The lock is a row in that
  table.
- `use_lockfile = true` — **native S3 locking** via conditional writes. No DynamoDB table
  exists; the lock is an object beside the state file. Requires OpenTofu/Terraform **1.10+**.

An entry that assumes a lock table will send you hunting for one that was never created.

**Likely causes:**
- A concurrent run — most often a `run --all` in CI overlapping with a local run.
- A previous process killed before it released the lock.
- Read access to the state but not write access to the lock, which surfaces here rather than
  as a permissions error.

**Solutions:**

```bash
# The lock ID is printed in the error. Run this in the unit that is stuck:
terragrunt force-unlock <LOCK_ID>

# Verify nothing is actually still running first. With DynamoDB locking:
aws dynamodb scan --table-name <lock-table> --max-items 5

# With use_lockfile, the lock is an object next to the state:
aws s3 ls s3://<bucket>/<key>.tflock
```

`force-unlock` is a shortcut for `terragrunt run -- force-unlock`, so it takes the same
`--working-dir` / `--config` flags as any other run. **Do not force-unlock a lock a live apply
still holds** — that is how two applies end up writing one state file.

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

## ERROR: Failed to get existing workspaces
**Category:** state

`init` cannot list workspaces from the backend.

**This is usually not a workspace problem.** Listing workspaces is the first thing that talks
to the backend, so a credential, permission or bucket problem surfaces with this wording
before anything mentions S3 or storage. Read it as "the backend did not answer" and check the
backend entries in this file first.

**Likely causes:**
- The backend does not exist yet, or the principal cannot list it (S3 `ListBucket`, GCS
  `storage.objects.list`, Azure data-plane RBAC).
- Credentials expired mid-session — common with short-lived SSO or assumed roles.
- The workspace genuinely does not exist, which is the least likely of these.

**Solutions:**

```bash
# Confirm who you are before blaming the config:
aws sts get-caller-identity      # or: az account show / gcloud auth list

terragrunt init
terragrunt workspace list
```

If the backend itself is missing, see "S3 bucket does not exist" / "GCS bucket not found" —
Terragrunt does not create it by default.

Verified against terragrunt 1.1.3 and the docs of 2026-08-20.

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
