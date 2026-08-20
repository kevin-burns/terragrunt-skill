# Terragrunt + Azure: remote state, provider setup & gotchas (1.x)

> Scope: how Terragrunt 1.x works with the **Azure (`azurerm`) backend** and the
> **`azurerm` provider**. Terragrunt orchestrates OpenTofu/Terraform, so Azure auth,
> backend keys, and most gotchas come from the *native* `azurerm` backend and provider —
> not from Terragrunt itself.
>
> Verified June 2026 against docs.terragrunt.com, the HashiCorp `azurerm` backend docs
> (developer.hashicorp.com/terraform/language/backend/azurerm), the OpenTofu equivalent,
> and Microsoft Learn. **Updated 2026-08-05 for Terragrunt v1.1.2** (2026-07-29), which
> changed the headline answer: the `azure-backend` experiment is still an experiment and has
> not graduated, but it is no longer inert — with it enabled on v1.1.2+ Terragrunt *does*
> bootstrap, converge, delete and migrate Azure state resources. On the default path, and on
> anything below v1.1.2, it still creates nothing. Grep-friendly: `grep -n '^## ' azure-backend.md`.

## THE ONE THING TO GET RIGHT: ask which version, then which flags

For S3 and GCS, Terragrunt natively **auto-provisions** the backend (bucket, lock table)
and supports `backend bootstrap` / `backend migrate` / `backend delete`. **Azure is
different**, and the answer changed in **v1.1.2** (2026-07-29). Establish the user's version
before advising, because the two answers are opposites.

**Default on every version, and on anything below v1.1.2 — Terragrunt creates nothing.**

- `terragrunt backend bootstrap` does **NOT** create the storage account or container.
- `terragrunt backend migrate` / `delete` do **NOT** act on Azure resources (migrate falls
  back to the OpenTofu/Terraform CLI).
- `remote_state { backend = "azurerm" }` behaves like a `generate` block: it writes the
  backend config but creates nothing.

So unless the user is on v1.1.2+ *and* has the experiment on, **the storage account + blob
container MUST already exist** before `terragrunt … init`. Provision them out-of-band — `az`
CLI, Bicep/ARM, or a dedicated bootstrap unit (run with local state, or a chicken-and-egg
shared account created once by hand). The `az` recipe below stays the default path.

**v1.1.2+ with `--experiment azure-backend` — Terragrunt does manage it.** Still opt-in, and
still an experiment, so it may change again. With the experiment enabled Terragrunt can
bootstrap the resource group, storage account and blob container behind
`remote_state { backend = "azurerm" }`, detect whether the backend needs bootstrapping,
converge blob versioning and soft-delete settings, delete state blobs or containers, and
migrate state blobs within the same storage account.

Terragrunt-only settings — `location`, the storage account SKU options, the `skip_*` flags,
`enable_soft_delete`, `soft_delete_retention_days` and `msi_resource_id` — are consumed by
Terragrunt and stripped before it runs OpenTofu/Terraform with `init -backend-config`, so the
underlying `azurerm` backend only receives keys it understands. Note `msi_resource_id` is not
bootstrap-only: it also selects the managed identity used for delete and migrate.

```bash
terragrunt --experiment azure-backend run -- plan
```

Before v1.1.2 this file said flatly "never tell a user Terragrunt will bootstrap Azure
state". That was correct for two years and is now correct only for the default path, which is
why the version question comes first. Do not carry the old blanket claim forward, and do not
assume the new behaviour either — it is gated twice, on version and on the experiment flag.

Docs: https://docs.terragrunt.com/features/units/state-backend/ ·
https://docs.terragrunt.com/reference/experiments/active#azure-backend ·
v1.1.2 release notes: https://github.com/gruntwork-io/terragrunt/releases/tag/v1.1.2

### Minimal bootstrap of the state storage with `az` (run once, out-of-band)
```bash
az group create -n terraform-rg -l eastus
az storage account create -n myterragruntstate -g terraform-rg -l eastus \
  --sku Standard_LRS --kind StorageV2 \
  --allow-shared-key-access false          # enterprise default: force Entra ID auth
az storage container create -n tfstate --account-name myterragruntstate \
  --auth-mode login
# Grant the deploying identity data-plane access (see RBAC gotcha below):
az role assignment create --assignee <objectId> \
  --role "Storage Blob Data Contributor" \
  --scope $(az storage account show -n myterragruntstate -g terraform-rg --query id -o tsv)
```

## remote_state for azurerm (the Terragrunt side)

`config` is a pure pass-through to the native `azurerm` backend. The Terragrunt docs show:

```hcl
remote_state {
  backend = "azurerm"
  config = {
    storage_account_name = "myterragruntstate"
    container_name       = "tfstate"
    key                  = "${path_relative_to_include()}/terraform.tfstate"
    resource_group_name  = "terraform-rg"
    subscription_id      = "00000000-0000-0000-0000-000000000000"
    use_azuread_auth     = true
  }
  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
}
```
Put this in `root.hcl` so every unit gets a unique state path via
`${path_relative_to_include()}`.

## azurerm BACKEND config keys (required vs optional)

Authoritative list: HashiCorp/OpenTofu `azurerm` backend docs (Terragrunt passes these
through unchanged).

**Always required (every auth method):**
| Key | Purpose |
|---|---|
| `storage_account_name` | the state storage account |
| `container_name` | the blob container |
| `key` | blob name for the state file (e.g. `prod/vpc/terraform.tfstate`) |

**Conditionally required / commonly set:**
- `resource_group_name` — **optional in general**; only required when
  `lookup_blob_endpoint = true` (management-plane lookup of the blob endpoint). MS Learn
  examples include it by convention; with direct Entra ID data-plane auth it can be omitted.
- `subscription_id` — optional **for the backend** (only needed for management-plane
  queries). **Do not confuse with the provider**, where v4+ makes it required (see below).
- `tenant_id` — needed with Entra ID / OIDC / service-principal auth.

**Auth + behavior keys (all optional):** `use_azuread_auth`, `use_oidc`, `use_msi`,
`use_cli`, `client_id`, `client_secret`, `client_certificate_path`,
`client_certificate_password`, `access_key`, `sas_token`, `snapshot` (default `false`),
`environment` (`public`|`china`|`usgovernment`, default `public`),
`lookup_blob_endpoint` (default `false`), `metadata_host`, `use_aks_workload_identity`.

Each has an `ARM_*` env-var equivalent (e.g. `ARM_USE_AZUREAD`, `ARM_CLIENT_ID`,
`ARM_SUBSCRIPTION_ID`). Canonical key list:
https://developer.hashicorp.com/terraform/language/backend/azurerm

## Authentication methods (recommended order)

The backend docs do not publish a strict precedence; methods, best first:

1. **Microsoft Entra ID (recommended)** — `use_azuread_auth = true` (`ARM_USE_AZUREAD`).
   OAuth tokens against the storage *data plane* instead of a shared key. Requires
   `tenant_id` and a data-plane RBAC role (below).
2. **OIDC / Workload Identity Federation (recommended for CI)** — `use_oidc = true`
   (`ARM_USE_OIDC`). No long-lived secret. See the OIDC section.
3. **Managed Identity (MSI)** — `use_msi = true` (`ARM_USE_MSI`); `client_id` for a
   user-assigned identity. Good for self-hosted runners / VMs.
4. **Azure CLI** — `use_cli = true` (`ARM_USE_CLI`); uses the `az login` session. Best for
   local dev.
5. **Service principal — client secret** — `client_id` + `client_secret` + `tenant_id`
   (`ARM_CLIENT_SECRET`). Not recommended for new workloads.
6. **Service principal — client certificate** — `client_id` + `client_certificate_path`
   (+ password) + `tenant_id`.
7. **Access key / SAS token** — `access_key` (`ARM_ACCESS_KEY`) / `sas_token`. Shared-key
   based; **avoid** — usually disabled by policy (see gotcha).

### `use_azuread_auth`
Enables Microsoft Entra ID auth to the storage account data plane instead of the account
shared key. Microsoft explicitly recommends Entra ID over Shared Key ("superior security
and ease of use… recommended by Microsoft"). Prefer `use_azuread_auth = true` for all new
configs. (Its documented default value is not stated on the backend reference; observed
behavior is shared-key auth when nothing is set — i.e. effectively `false` — so set it
explicitly rather than relying on a default.)

## azurerm PROVIDER setup (generate a provider block)

Terragrunt has no Azure-specific provider feature — generate `provider.tf` like any other
provider via a `generate` block (see templates/providers/azure-generate-provider.hcl):

```hcl
generate "provider" {
  path      = "provider.tf"
  if_exists = "overwrite_terragrunt"
  contents  = <<EOF
provider "azurerm" {
  features {}
  subscription_id = "00000000-0000-0000-0000-000000000000"  # REQUIRED in v4+
  use_azuread_auth = true
}
EOF
}
```

### GOTCHA — provider v4 requires `subscription_id`
**Breaking change in `azurerm` provider v4.0.0 (2024-08-22):** you must specify the Azure
Subscription ID when configuring the provider — set `subscription_id` in the `provider`
block **or** the `ARM_SUBSCRIPTION_ID` env var. (The change makes the provider's target
subscription explicit rather than inferred; see the v4 upgrade guide for the rationale.)

Nuances:
- v4.0.1 (2024-08-23) fixed an over-broad bug that blocked `terraform validate` when
  `subscription_id` was unset.
- v4.35.0 (2025-07-01) relaxed it: `subscription_id` may be omitted **when `use_cli = true`**
  (the provider infers it from the active `az` session). All other auth methods still
  require it.

**Rule of thumb:** always set `subscription_id` (or `ARM_SUBSCRIPTION_ID`) on v4+. Only
CLI-auth pipelines on ≥ v4.35.0 may omit it. Pin the provider version (`required_providers`)
so this behavior is predictable.

## Gotchas (the ones that actually bite)

### 1. Shared-key access disabled → 403 on `init`
Enterprise policy commonly sets `allowSharedKeyAccess = false` on the storage account. The
backend's default shared-key path then fails with **403 (Forbidden)** — "Azure Storage
rejects all subsequent requests… authorized with the account access keys." **Fix:**
`use_azuread_auth = true` (or `use_oidc`/`use_msi`) plus a data-plane RBAC role.

### 2. ARM Owner/Contributor is NOT enough for blob data
With Entra ID auth the identity needs a **data-plane** role on the container/account:
- **Storage Blob Data Contributor** — read/write/delete (minimum for state operations).
- **Storage Blob Data Owner** — full, incl. POSIX ACLs.

The ARM management roles **Owner / Contributor / Storage Account Contributor do NOT grant
blob data access via Entra ID** — they manage the account, not its data. This surprises
people constantly. Role assignments can take ~10 min (up to 30 at MG scope) to propagate.

### 3. Storage account & container must pre-exist
Covered above — OpenTofu/Terraform will not create the backend storage. "Before you use
Azure Storage as a backend, you must create a storage account."

### 4. State locking is automatic via blob lease
The `azurerm` backend locks the state blob before any write (native blob lease) — no
DynamoDB-equivalent table is needed (contrast S3). Concurrency safety is built in; a stuck
lease may need a manual break (`az storage blob lease break`).

### 5. Sovereign clouds
For Azure Government / China set `environment` (`usgovernment` / `china`) in the backend
config or `ARM_ENVIRONMENT`; default is `public`.

## OIDC / Workload Identity Federation for CI (no secrets)

Set `use_oidc = true` and supply the federated-credential identity:

| Backend/provider key | Env var | Meaning |
|---|---|---|
| `use_oidc` | `ARM_USE_OIDC` | enable OIDC |
| `client_id` | `ARM_CLIENT_ID` | app/UAMI client ID |
| `tenant_id` | `ARM_TENANT_ID` | Entra tenant |
| `subscription_id` | `ARM_SUBSCRIPTION_ID` | subscription (provider v4+ needs it) |
| `oidc_request_url` | `ARM_OIDC_REQUEST_URL` | IdP token request URL |
| `oidc_request_token` | `ARM_OIDC_REQUEST_TOKEN` | bearer token for the request |
| `oidc_token` | `ARM_OIDC_TOKEN` | pre-obtained ID token |
| `oidc_token_file_path` | `ARM_OIDC_TOKEN_FILE_PATH` | file holding the ID token |
| `ado_pipeline_service_connection_id` | `ARM_ADO_PIPELINE_SERVICE_CONNECTION_ID` (checked first) or `ARM_OIDC_AZURE_SERVICE_CONNECTION_ID` | Azure DevOps service connection |

- **GitHub Actions:** the runner exposes `ACTIONS_ID_TOKEN_REQUEST_URL` /
  `ACTIONS_ID_TOKEN_REQUEST_TOKEN`; map them to `ARM_OIDC_REQUEST_URL` /
  `ARM_OIDC_REQUEST_TOKEN` (and set `permissions: id-token: write`).
- **Azure DevOps:** use `ARM_OIDC_AZURE_SERVICE_CONNECTION_ID`.

Configure OIDC identically on the `provider "azurerm"` block (same keys/env vars) so both
the backend and resource operations federate.

## Quick checklist for an Azure Terragrunt setup
```
[ ] Storage account + container created out-of-band — unless on v1.1.2+ with `--experiment azure-backend`, which does bootstrap them
[ ] allow_shared_key_access=false  →  use_azuread_auth = true in remote_state config
[ ] Deploying identity has "Storage Blob Data Contributor" on the account/container
[ ] remote_state in root.hcl, key = "${path_relative_to_include()}/terraform.tfstate"
[ ] provider "azurerm" generated with features {} and subscription_id (v4+ required)
[ ] CI: use_oidc = true + federated credential (no client_secret in the repo)
[ ] required_providers pins azurerm (so the v4 subscription_id rule is predictable)
```

## Sources
- Terragrunt state backend: https://docs.terragrunt.com/features/units/state-backend/
- Terragrunt experiments (`azure-backend`): https://docs.terragrunt.com/reference/experiments/active
- azurerm backend keys/auth: https://developer.hashicorp.com/terraform/language/backend/azurerm
- azurerm provider v4 (subscription_id): https://learn.microsoft.com/azure/developer/terraform/provider-history/provider-version-history-azurerm-4-0-0-to-current
- State in Azure Storage (locking, pre-existing): https://learn.microsoft.com/azure/developer/terraform/store-state-in-azure-storage
- Prevent Shared Key authorization (403): https://learn.microsoft.com/azure/storage/common/shared-key-authorization-prevent
- Authorize blob access with Entra ID (RBAC roles): https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory
