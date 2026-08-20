---
name: terragrunt-skill
license: MIT
description: Comprehensive Terragrunt 1.x skill for generating, validating, reviewing, and debugging Terragrunt configurations (root.hcl, terragrunt.hcl, terragrunt.stack.hcl, units, stacks, catalogs) across AWS, Azure, and GCP. Use this skill whenever the user mentions Terragrunt, terragrunt.hcl, root.hcl, stack files, units, HCL orchestration of OpenTofu/Terraform, remote state DRY configuration, run --all, dependency blocks between modules, or asks to scaffold/lint/diagnose multi-environment IaC layouts — even if they don't say "Terragrunt" explicitly but show Terragrunt HCL.
---

# Terragrunt (1.x)

Single skill for all Terragrunt work, organized as a router: identify the task mode below,
read ONLY the listed reference(s), then act. References are grep-friendly — prefer
`grep` lookups over reading whole files.

## Hard policy

1. **Post-1.0 CLI only.** Never generate or recommend pre-1.0 forms: `run-all`,
   `plan-all`, `hclfmt`, `hclvalidate`, `graph-dependencies`, `validate-inputs`,
   `terragrunt-` prefixed flags, the `skip` attribute, `retryable_errors`, or bare
   `find_in_parent_folders()` pointing at a root `terragrunt.hcl`. If user code contains
   these, flag them and propose the 1.x form.
2. **Fact-based generation.** Every generated pattern must trace to a documented Gruntwork
   pattern (references here carry doc links to docs.terragrunt.com). Don't invent layouts.
3. **Knowledge freshness. This skill does not assert what the current Terragrunt release is.**
   That claim has a half-life of about six weeks and it expired unnoticed: this line said
   "current stable v1.1.2" while the binary on the author's own machine was already v1.1.3.
   Run **`scripts/preflight.py`** instead — it reads `terragrunt --version` and reports which
   of the gates below your build satisfies, which it does not reach, and which upgrade hazards
   are in effect on it. Everything that follows is a fact about *when a feature landed*, which
   does not rot. **v1.1.0 graduated six experiments to
   GA** — `stack-dependencies`, `cas`, `catalog-redesign`, `mark-many-as-read`,
   `opt-out-auth`, `dag-queue-display` — so their features are now **enabled by default**;
   passing the old `--experiment`/`TG_EXPERIMENT` value only prints a "completed experiment"
   warning. The stack-dependency features (`autoinclude`, `unit.<name>.path` /
   `stack.<name>.path`, `dependency` on stack dirs via `autoinclude`) and the CAS attributes
   (`update_source_with_cas`, `mutable`) therefore require **v1.1.0+** — flag them and do NOT
   emit them for repos pinned to ≤1.0.x.

   **v1.1.1 added two experiments** (opt-in, not GA), both on the `terraform` block and both
   requiring **v1.1.1+**: `oci` (module sources from OCI registries via `oci://`) and
   `version-attribute` (a `version` constraint for `tfr://` registry modules). Syntax and the
   gating rules are in `references/hcl-blocks.md` under `## BLOCK: terraform`. v1.1.1 was
   otherwise a bug-fix release — it introduced no new GA surface.

   **v1.1.2 added no new GA surface either, but two of its fixes change what to advise.**
   Recommend **v1.1.2+** rather than v1.1.1 wherever either applies:
   - The **provider cache server**'s archive-download endpoint did not require the run's
     token before v1.1.2, so another local process could use a running cache server to pull
     from a private registry with the starting user's registry credentials. Relevant on
     shared CI runners. See `references/scale-and-performance.md`.
   - **v1.1.1 specifically broke `iam_role`** (and `--iam-assume-role` / `TG_IAM_ASSUME_ROLE`)
     when combined with static AWS credentials: backend operations assumed the role a second
     time, so it tried to assume itself and AWS returned `AccessDenied`. The error points at
     the trust policy, but editing the trust policy is the wrong fix — upgrading is. See
     `references/hcl-blocks.md` under `## BLOCK: iam_role`.

   **v1.1.3 graduated nothing.** No experiment stabilised, so the "enabled by default" list
   above is unchanged from v1.1.0. It is twelve bug fixes and five new experiments, but two
   items in it change what to advise and one changes behaviour whether or not you opt in.

   **Recommend v1.1.3+ wherever `--provider-cache` is used, or wherever two Terragrunt runs
   can overlap on one machine.** Two separate race conditions were fixed, and both are the
   same shape as the v1.1.2 provider-cache issue above:
   - The cache server could start answering requests before it had finished preparing its
     directories. A provider requested in that window had its archive and lock file written
     **relative to the working directory**, leaving zip files loose in the project.
   - Two concurrent runs staged provider downloads at the same path, so the first to finish
     could delete an archive the other was still unpacking, failing it with
     `failed to open zip archive`. Relevant to any parallel CI matrix on a shared runner.
   See `references/scale-and-performance.md`.

   **THE ONE THAT BITES WITHOUT OPTING IN: `(` and `)` are now reserved in `--filter`.** The
   `bounded-discovery` experiment introduces an inline `(dir)` boundary operand, and reserving
   those characters **changes how `--filter` parses everywhere, not only when the experiment is
   enabled**. `--filter '1...(foo | bar)'` previously matched a unit literally named `(foo` or
   `bar)`; on v1.1.3 it is rejected as a malformed boundary. Wrap a name or path containing
   parentheses in braces — `--filter '{./weird(name)}'` — to keep it literal. This is the
   v1.1.1-`iam_role`-shaped item for this release: an upgrade can break a working invocation
   with nothing enabled. Check filter strings and unit names for parentheses before upgrading.

   **v1.1.3 added five experiments, all opt-in, none GA:** `block-iteration` (reserves the
   `expansion` block for iterating `dependency`/`unit`/`stack` over `count`/`for_each`, plus an
   `enabled` attribute on `unit` and `stack` — **reserved only in this release, enabling it has
   no behavioural effect**, but writing `expansion` *without* it is now an error rather than a
   silent discard), `bounded-discovery` (above), `browse-tui` (`terragrunt browse`, a
   three-column TUI estate browser), `mutable-generate` (see the collision warning below) and
   `optional-dependency-outputs` (`--no-dependency-outputs`, the global form of
   `skip_outputs`). Syntax and gating in `references/hcl-blocks.md`.

   **NAME COLLISION — `mutable` now means two different things.** On the **`unit`** block it is
   GA since v1.1.0 and needs no experiment. On the **`generate`** block it is new in v1.1.3 and
   requires `--experiment mutable-generate`; setting it without the experiment is an error, and
   earlier versions reject the attribute outright. Do not carry the v1.1.0 gate across to
   `generate`. Both are in `references/hcl-blocks.md`.

   **Experiments are not a short list, and they move in patch releases.** Alongside the two
   above, `azure-backend`, `deep-merge`, `dependency-fetch-output-from-state`,
   `hook-context-env`, `iac-engine`, `optional-hooks`, `slow-task-reporting` and `symlinks`
   were active as of v1.1.1, and **v1.1.2 added `otel-logs`** (OpenTelemetry logs signal via
   `TG_TELEMETRY_LOGS_EXPORTER`) **and `profiling`** (pprof CPU/heap/goroutine collection for
   debugging Terragrunt itself, not the infrastructure it manages) — twelve active as of
   v1.1.2 — **and that count was already short by one: `catalog-format` was active and is not
   in the list above.** The authoritative list gives **eighteen active as of v1.1.3**, so do not
   reach the number by adding this release's five to a previous total; read the page.
   v1.1.2 also changed two existing ones: `azure-backend` went from inert to
   functional (see `references/azure-backend.md` — this reverses a long-standing "Terragrunt
   never bootstraps Azure state" rule), and `oci` gained CAS caching plus Docker
   credential-helper auth. These references cover only some of them, so an unfamiliar
   `--experiment` value
   is not evidence that it is wrong — look it up rather than flagging it. For anything newer,
   niche, or not found in the references, use the C7 search skill (Context7) or fetch
   docs.terragrunt.com directly — do not guess.
4. Terragrunt orchestrates **OpenTofu or Terraform**; don't assume one unless the user's
   repo indicates it (`.terraform-version`, `terraform_binary`, provider constraints, or an
   `engine` block — the latter is gated behind the `iac-engine` experiment and is not covered
   in `references/hcl-blocks.md`, so look it up before editing one).

## Terminology (1.0)

**Unit** = directory with `terragrunt.hcl` deploying one module. **Stack** = group of units;
*implicit* (directory tree) or *explicit* (`terragrunt.stack.hcl`). **Catalog** = library of
reusable unit/module definitions. Targeting uses `--filter` expressions.

## Mode router

| Task | Mode | Read first |
|---|---|---|
| "Create/scaffold/set up" configs, envs, stacks | GENERATE | references/architecture-patterns.md + relevant templates/ |
| "Validate/lint/check/CI" existing configs | VALIDATE | validate.sh header (abs path in VALIDATE workflow); references/cli-reference.md as needed |
| "Review/audit/best practice" a repo or file | REVIEW | references/best-practices.md |
| Error message pasted / "why is this failing" | DIAGNOSE | grep references/error-patterns.md |
| "What does X do" (block/function/command) | LOOKUP | grep the matching reference below |
| Complex/edge-case examples (multi-account, CI, mocks) | EXAMPLES | references/advanced-examples.md |
| Anything Azure backend/provider (state, auth, gotchas) | (any mode) | **also** references/azure-backend.md |
| "Only run changed units", slow `run --all`, CI fan-out, performance at scale | SCALE | references/scale-and-performance.md |
| CI/CD pipeline, OIDC auth to AWS/GCP/Azure, saving plans between plan and apply | CICD | references/cicd.md |
| Look up a module, a resource type, or their inputs/outputs — before pinning a `source` or writing `inputs` | *(hand off)* | the [`terraform-registry`](https://github.com/kevin-burns/claude-skills/tree/main/terraform-registry) skill, not this one |
| "Migrate to stacks", convert an `_envcommon`/tree layout to `terragrunt.stack.hcl` | MIGRATE | references/architecture-patterns.md `## PATTERN: migrate an existing tree to explicit stacks` |

## Reference index (grep, don't read whole files)

**Quick navigation.** Every reference is written to be grepped by a heading convention, so
the fastest route to an answer is the grep handle, not the filename.

| Reference | Holds | Entries | Grep handle |
|---|---|---|---|
| `error-patterns.md` | diagnosed errors: likely causes for every one, a fix for 17 | 69 | `^## ERROR:` |
| `functions.md` | built-in functions by category | 31 | `^## FUNCTION:` |
| `best-practices.md` | practices, plus comparisons and decision guides | 29 / 7 / 3 | `^## PRACTICE:` `^## COMPARISON:` `^## DECISION:` |
| `cli-reference.md` | the 1.x command tree and the `--filter` system | 24 | `^## COMMAND:` |
| `hcl-blocks.md` | every HCL block and attribute | 15 / 10 | `^## BLOCK:` `^## ATTRIBUTE:` |
| `advanced-examples.md` | worked examples: multi-account/subscription/project, CI, mocks, AVM, CFT, own-module | 28 | `^## EXAMPLE:` |
| `architecture-patterns.md` | layout patterns, catalog/live repo shape, migration to stacks | 6 | `^## PATTERN:` |
| `cicd.md` | OIDC per cloud, plan-then-apply across a stack | — | grep a `^## ` heading |
| `azure-backend.md` | Azure state, auth and provider gotchas | — | read whole; it is short |
| `scale-and-performance.md` | run only what changed, cache, parallelism | — | read whole; it is short |

Two of the ten carry no heading convention because they are short enough to read end to end.
Counts are verified against the files, not asserted: regenerate with
`grep -c '^## ERROR:' references/error-patterns.md` and so on.


- `references/architecture-patterns.md` — layout patterns, env-agnostic root rule, unit/stack
  model, dependency wiring, runtime control. Headings: `## PATTERN:`
- `references/hcl-blocks.md` — all HCL blocks (terraform, remote_state, dependency, include,
  generate, locals, inputs, feature, exclude, errors...). `grep '^## BLOCK: dependency'`
- `references/functions.md` — built-in functions by category. `grep '^## FUNCTION: get_env'`
- `references/cli-reference.md` — full 1.0 command tree + `--filter` system.
  `grep '^## COMMAND: stack run'`
- `references/error-patterns.md` — 69 diagnosed errors. Every one names likely causes; **17
  carry a fix**, and an entry with no `**Solutions:**` section has none to give — say so
  rather than improvising one. Grep error keywords first:
  `grep -in 'state lock' references/error-patterns.md`
- `references/best-practices.md` — practices with priority/rationale/antipatterns, plus
  `## COMPARISON:` (e.g. dependency vs dependencies) and `## DECISION:` guides
- `references/advanced-examples.md` — 28 worked examples. `grep '^## EXAMPLE:'`
- `references/azure-backend.md` — Azure (`azurerm`) remote state + provider setup and
  gotchas: whether Terragrunt bootstraps Azure depends on version + experiment
  (no by default, yes on v1.1.2+ with `--experiment azure-backend`), backend key list, auth methods,
  `use_azuread_auth`/Entra ID, provider v4 `subscription_id`, RBAC + shared-key gotchas,
  OIDC for CI. Read this for ANY Azure backend/provider task.
- `references/cicd.md` — CI/CD: OIDC to AWS (incl. the immutable `sub` claim that breaks
  pipelines on repos created from 2026-07-15), GCP Workload Identity Federation, a pointer to
  the Azure section, and `--out-dir` for saving a plan per unit between plan and apply. Read
  for anything about pipelines or CI authentication.
- `references/scale-and-performance.md` — running only changed units/stacks at scale:
  `--filter` git+graph targeting (`--filter-affected`), `find --json` CI matrices, provider
  cache server, CAS, dependency-output-from-state, parallelism, per-unit overhead, OSS vs
  paid Scale. Read for "only plan/apply what changed", slow `run --all`, or CI fan-out.

## Templates

- `templates/root/root.hcl` — root config (environment-agnostic)
- `templates/child/terragrunt.hcl` — unit including root + env.hcl
- `templates/env/env.hcl` — per-environment locals
- `templates/stack/terragrunt.stack.hcl`, `templates/catalog/` — explicit stacks & catalog units
- `templates/module/terragrunt.hcl` — standalone unit
- `templates/backends/` — remote_state for S3/GCS/Azure, essential + advanced tiers.
  **Azure caveat:** by default `azurerm` passes through to the native backend and
  Terragrunt does NOT bootstrap/migrate/delete Azure storage, so the account/container
  must pre-exist — which is what these templates assume. On **v1.1.2+ with
  `--experiment azure-backend`** that reverses and Terragrunt does manage them. Establish
  the version before advising; full detail in `references/azure-backend.md`.
- `templates/providers/` — provider `generate` blocks for all three clouds
  (`aws-generate-provider.hcl`, `azure-generate-provider.hcl`, `gcp-generate-provider.hcl`).
  **Each cloud constrains the target differently, and one of them does not constrain it at
  all:** AWS has `allowed_account_ids`; `azurerm` v4+ makes `subscription_id` **required**
  (see `references/azure-backend.md`); the `google` provider has **no equivalent and no
  required argument whatsoever**, so an unset `project` falls through to `GOOGLE_PROJECT`,
  then ADC, then whatever `gcloud config set project` last selected. Derive `project` from
  the directory tree rather than typing it.

Replace ALL placeholder variables before presenting (`{{mustache}}` in templates/backends and
templates/providers; `[BRACKET]` style everywhere else); never leave placeholders or invent
secrets/account IDs — ask or use obvious dummies labelled as such.

## GENERATE workflow

1. Determine pattern via references/architecture-patterns.md; output the pattern selection
   checklist (in that file) before writing files.
2. Read the relevant template(s); adapt, don't freestyle.
3. Verify the include/read graph: every `find_in_parent_folders`/`read_terragrunt_config`
   target must exist from the referencing file's location.
4. Validate if tooling exists (see VALIDATE); otherwise state what wasn't validated.
5. Present: directory tree, file list, run commands (`terragrunt run --all plan`), and any
   placeholders the user must fill.

## VALIDATE workflow

> **Bundled scripts run by absolute path.** They live in this skill's base directory (announced
> when the skill loads, usually `~/.claude/skills/terragrunt-skill`). You'll be working inside an
> IaC repo, so a relative `scripts/…` won't resolve — always use the base-dir path. The Python
> helper is stdlib-only: prefer `uv run python <path>`, falling back to `python3 <path>` if uv
> isn't on PATH (`UV="$(command -v uv || ls "$HOME/.local/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv 2>/dev/null | head -1)"`).

`bash ~/.claude/skills/terragrunt-skill/scripts/validate.sh [DIR]` runs the layered suite:
`hcl fmt --check`, `hcl validate`, tflint, Trivy, dag check, optional plan. Control via env
vars: `SKIP_PLAN`, `SKIP_SECURITY`, `SKIP_LINT`, `SKIP_INIT`, `SKIP_BACKEND_INIT=true`
(CI/offline: init with `-backend=false`), `SOFT_FAIL_SECURITY`. No terragrunt binary available?
Fall back to static review: check 1.0-only policy violations, include-graph integrity, then
REVIEW mode checklist. `uv run python ~/.claude/skills/terragrunt-skill/scripts/detect_custom_resources.py [DIR]`
finds non-registry providers/modules needing research.

## DIAGNOSE workflow

1. Extract distinctive tokens from the error (e.g. "state lock", "Could not find").
2. `grep -in '<token>' references/error-patterns.md`; read matched `## ERROR:` sections.
3. No match → C7 search / docs.terragrunt.com troubleshooting; say the pattern wasn't in the
   embedded set.

## REVIEW workflow

Audit against best-practices.md as a checklist; report findings ordered by priority with the
practice name, why it matters, and the doc link. Include 1.0-policy violations (Hard policy
item 1) as findings.

## Provenance

This skill is MIT licensed. It is **not** wholly original, and the parts that are not are
named here.

**Harvested content.** Five reference files — `advanced-examples.md`, `best-practices.md`,
`error-patterns.md`, `functions.md` and `hcl-blocks.md` — began as curated data from
[omattsson/terragrunt-mcp-server](https://github.com/omattsson/terragrunt-mcp-server)
(MIT), restructured here for grep-based lookup and since re-checked against
docs.terragrunt.com. Each file repeats this in its own header. Together they are roughly
two-thirds of the reference corpus by size, so it is the single largest input to this skill
after the Terragrunt documentation itself.

  Two things follow, and both matter. **MIT permits the reuse and requires the notice**, which
  is why this paragraph exists. And that repository's last commit predates Terragrunt v1.0.0
  by five weeks, so anything harvested from it is **pre-1.0 material by default** — the
  re-checks are what make it safe, not the source. Where a re-check has not happened, treat
  the entry as suspect rather than current. `references/hcl-blocks.md` is known to still carry
  three pre-1.0 retry blocks for exactly this reason.

**Layout and scaffolding guidance** describes, but does not copy, Gruntwork's published
reference repositories:
[terragrunt-infrastructure-catalog-example](https://github.com/gruntwork-io/terragrunt-infrastructure-catalog-example)
(MPL-2.0),
[terragrunt-infrastructure-live-example](https://github.com/gruntwork-io/terragrunt-infrastructure-live-example)
(Apache-2.0), and [gruntwork-io/boilerplate](https://github.com/gruntwork-io/boilerplate)
(MPL-2.0), the templating engine behind `scaffold` and `catalog`.

**Terragrunt** is © Gruntwork, Inc. (MIT). This skill is not affiliated with or endorsed by
Gruntwork. The bundled `scripts/validate.sh` invokes external tools when present —
`terragrunt`, `tflint` (MPL-2.0) and `trivy` (Apache-2.0) — but does not bundle them; their
own licenses apply.
