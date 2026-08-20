# CI/CD for Terragrunt

> Verified against the cited sources on **2026-08-19**. Every version, flag and claim below
> carries its source; where a source was read as a summary rather than raw, it says so.
> Flag and avoid any pre-1.0 idioms.

Lookup: grep a heading — `grep -n '^## ' cicd.md`. The pipeline mechanics that are NOT here
live in `scale-and-performance.md` (targeting changed units, CI matrices, the provider cache
server, parallelism, exit codes) and `best-practices.md` (plan/apply separation as a practice,
pipeline-as-the-only-path-to-production). This file is **authentication and pipeline shape**.

Gruntwork's own CI guide (<https://docs.terragrunt.com/guides/ci-with-terragrunt/>) names four
properties a good IaC pipeline has — plan on every pull request, apply on merge to main,
DAG-aware orchestration, and OIDC-based authentication — and then recommends their commercial
Terragrunt Scale product rather than showing a pipeline. It contains **no pipeline YAML**.
That is why this file exists.

---

## Plan then apply across a stack: `--out-dir`

**This is the 1.x mechanism and it is the part most pipelines get wrong.** A single
`-out=tfplan` cannot work across many units, because the path is relative to each unit.
`--out-dir` writes one plan per unit, mirroring the stack's directory structure.

```bash
# Plan every unit, saving a plan file per unit under /tmp/tfplan
terragrunt run --all --out-dir /tmp/tfplan -- plan

# Apply consumes those saved plans
terragrunt run --all --out-dir /tmp/tfplan -- apply
```

> "Performing a `run --all --out-dir <dir> -- apply` requires that a plan already exists for
> each unit in the stack. If a plan is missing for any unit, the command will fail."
> — <https://docs.terragrunt.com/features/stacks/run-queue#saving-opentofuterraform-plan-output>

**A filter must match between the plan and the apply.** Plan a narrower set than you apply and
the apply fails on the units with no saved plan:

```bash
terragrunt run --all --filter '<unit>...' --out-dir /tmp/tfplan -- plan
terragrunt run --all --filter '<unit>...' --out-dir /tmp/tfplan -- apply
```

`--json-out-dir` writes machine-readable plans alongside, for policy checks or a PR comment:

```bash
terragrunt run --all --out-dir /tmp/all --json-out-dir /tmp/all -- plan
```

**`run --all` with `apply` or `destroy` silently adds `-auto-approve`** — "due to issues with
shared `stdin` making individual approvals impossible"
(<https://docs.terragrunt.com/reference/cli/commands/run/>). Opt out with `--no-auto-approve`.
In a pipeline this is what you want; know that it is happening.

**Mind the `--`.** The documented form is `terragrunt run [flags] -- [tofu command]`. Flags
before the separator are Terragrunt's, everything after is passed through.

---

## OIDC: AWS

One OIDC provider, one role, no long-lived keys.

**Register the provider** with URL `https://token.actions.githubusercontent.com` and audience
`sts.amazonaws.com`
(<https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services>).

**Trust policy** — the two condition keys are `token.actions.githubusercontent.com:aud` and
`token.actions.githubusercontent.com:sub`:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
        "token.actions.githubusercontent.com:sub": "repo:<ORG>/<REPO>:ref:refs/heads/<BRANCH>"
      }
    }
  }]
}
```

Use `StringLike` with `repo:<ORG>/<REPO>:*` to allow any branch, or scope to an environment
with `repo:<ORG>/<REPO>:environment:prod`.

**In the workflow** — `aws-actions/configure-aws-credentials` (MIT; v6.2.3, 2026-07-22). Only
`role-to-assume` and `aws-region` are required:

```yaml
permissions:
  id-token: write
  contents: read

steps:
  - uses: aws-actions/configure-aws-credentials@v6
    with:
      role-to-assume: arn:aws:iam::<ACCOUNT_ID>:role/<ROLE>
      aws-region: eu-central-1
```

`role-session-name` defaults to `GitHubActions`. `audience` is only needed outside the default
partition — e.g. `sts.amazonaws.com.cn` in China regions.

## ERROR: Not authorized to perform sts:AssumeRoleWithWebIdentity (immutable `sub` claim)

**This one is new, dated, and breaks working pipelines.** From the
`aws-actions/configure-aws-credentials` README:

> "Repositories created on github.com on or after 15 July 2026, and older repositories that
> have opted in, emit an immutable `sub` claim. This claim appends the permanent numeric ID of
> the organization and of the repository after each name, separated by `@`, so that a recycled
> org or repository name cannot be used to mint tokens matching a stale trust policy."

```text
# Legacy (mutable)
repo:octo-org/octo-repo:ref:refs/heads/main

# Immutable
repo:octo-org@123456/octo-repo@789012:ref:refs/heads/main
```

> "If your trust policy matches the legacy name-only form and your repository emits the
> immutable claim, `AssumeRoleWithWebIdentity` fails with `Not authorized to perform
> sts:AssumeRoleWithWebIdentity`."

**The error names authorization, so the instinct is to widen the role's permissions. That is
the wrong fix and it will not work** — the trust policy's `sub` condition never matched, so no
permission change helps. Update the `sub` pattern.

Not determined on 2026-08-19: the `sub` format for tag-triggered workflows. GitHub's docs show
branch, environment and wildcard forms; no tag example was found and no consolidated table
exists. Check before writing a tag-scoped trust policy.

---

## OIDC: GCP

Workload Identity Federation, via `google-github-actions/auth` (Apache-2.0; v3, 2025-09-03).

**Direct WIF is the preferred form and needs no service account:**

```yaml
permissions:
  contents: read
  id-token: write

steps:
  - uses: google-github-actions/auth@v3
    with:
      project_id: my-project
      workload_identity_provider: projects/<NUM>/locations/global/workloadIdentityPools/github/providers/my-repo
```

> "Without this input, the GitHub Action will use Direct Workload Identity Federation. If this
> input is provided, the GitHub Action will use Workload Identity Federation through a Service
> Account." — the `service_account` input

**The exception that forces a service account:** Direct WIF yields a federated token only. To
mint OAuth 2.0 access tokens or ID tokens for downstream calls you must supply
`service_account` and use impersonation.

**Pool provider setup**, quoted from the same README:

```sh
gcloud iam workload-identity-pools providers create-oidc "my-repo" \
  --project="${PROJECT_ID}" \
  --location="global" \
  --workload-identity-pool="github" \
  --display-name="My GitHub repo Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
  --attribute-condition="assertion.repository_owner == '${GITHUB_ORG}'" \
  --issuer-uri="https://token.actions.githubusercontent.com"
```

> "🛑 CAUTION! Always add an Attribute Condition to restrict entry into the Workload Identity
> Pool... A good default option is to restrict admission based on your GitHub organization."

**No provider block is needed.** With its defaults (`create_credentials_file: true`,
`export_environment_variables: true`) the action writes a credentials file and exports
`GOOGLE_APPLICATION_CREDENTIALS`, which the Google Terraform provider picks up through its
documented Application Default Credentials fallback. Set either input to `false` and you must
wire credentials into the provider block yourself.

---

## OIDC: Azure

Covered in full in `azure-backend.md` — see `## OIDC / Workload Identity Federation for CI`.
Short version: `use_oidc = true` (`ARM_USE_OIDC`) plus a federated credential, and the
`oidc_request_url` / `oidc_request_token` / `oidc_token` / `oidc_token_file_path` table there.
Azure also needs a data-plane RBAC role for blob state; ARM Owner or Contributor is **not**
sufficient. That gotcha is in `azure-backend.md` and it is the one that costs the most time.

---

## The official action, and what it does not do

`gruntwork-io/terragrunt-action` (Apache-2.0; v3.4.1, 2026-07-23) installs pinned Terragrunt
and OpenTofu versions — via `mise.toml` or the `tg_version` / `tofu_version` inputs — and runs
a single `tg_command` in `tg_dir`, optionally posting output as a PR comment (`tg_comment`).
Minimum supported Terragrunt is 0.77.22.

**It is a thin per-unit wrapper, not an orchestrator.** It does not implement `run --all`
fan-out and it does not save or restore plan files across a stack. For a stack pipeline you are
writing the `run --all --out-dir` steps yourself, whatever action installs the binary. Note
also that `tg_add_approve` defaults to on.

`gruntwork-io/patcher-action` (Apache-2.0; v5.4.0, 2026-06-30) is a reusable workflow that
discovers, updates and raises PRs for Terragrunt dependencies. Dependency automation, not a
plan/apply pipeline.

---

## Sources

- <https://docs.terragrunt.com/features/stacks/run-queue#saving-opentofuterraform-plan-output> — `--out-dir`, filter matching (raw)
- <https://docs.terragrunt.com/reference/cli/commands/run/> — auto-approve behaviour (raw)
- <https://docs.terragrunt.com/guides/ci-with-terragrunt/> — the four properties; a Terragrunt Scale tutorial with no pipeline YAML (raw)
- <https://github.com/aws-actions/configure-aws-credentials> — inputs, trust policy, immutable `sub` (raw README; version and MIT licence via the GitHub API)
- <https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services> — provider URL, audience, `sub` forms (raw)
- <https://github.com/google-github-actions/auth> — Direct WIF, attribute mapping, exported credentials (raw README; version and Apache-2.0 via the API)
- <https://github.com/gruntwork-io/terragrunt-action>, <https://github.com/gruntwork-io/patcher-action> — raw READMEs and the API
- `hashicorp/terraform-provider-google` `provider_reference` — the ADC fallback (raw)
- <https://docs.terragrunt.com/migrate/cli-redesign/> — the v1.0 rename that deprecated `run-all` in favour of `run --all` (**summarised fetch, lower confidence**; consistent with the CLI docs, which use only the new form)
- Google Cloud WIF-with-deployment-pipelines docs (**summarised fetch, lower confidence**)
