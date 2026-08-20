# Terragrunt at scale: plan/apply only what changed (1.x)

> The problem: a repo with hundreds of units. `run --all plan/apply` walks the whole tree
> and is slow. This file is the OSS toolkit for **targeting only changed units + their
> dependents**, plus the caching/parallelism knobs that make large runs fast. Everything
> here is free CLI — the paid **Terragrunt Scale** platform only adds *hosted* orchestration
> on top (see the last section).
>
> Content spot-checked against docs.terragrunt.com at **v1.1.0** (2026-07-01); reviewed against the **v1.1.1** release notes (2026-07-14) on 2026-07-29 with no changes required — v1.1.1 was bug-fix only, and its two new experiments touch the `terraform` block (see hcl-blocks.md). Grep-friendly:
> `grep -n '^## ' scale-and-performance.md`.

## TL;DR recipes

```bash
# Plan only units changed vs the default branch (auto-detects main/master):
terragrunt run --all --filter-affected -- plan

# Plan changed units AND everything downstream of them (so you don't ship a changed
# module without re-planning its dependents):
terragrunt run --all --filter '[main...HEAD]' --filter '...[main...HEAD]' -- plan

# Enumerate affected units as JSON for a CI fan-out matrix (one runner per unit):
terragrunt find --json --filter-affected --dependencies --queue-construct-as=plan

# Make large --all runs fast: cache providers once, cap concurrency.
TG_PROVIDER_CACHE=1 terragrunt run --all --parallelism 8 -- apply
```

## Target only git-changed units (`--filter` git expressions)

The unified `--filter` flag is how you scope a run. Git expressions compare two refs and
match the units whose files changed.

- **Syntax:** `--filter '[<from>...<to>]'`, e.g. `'[main...HEAD]'`, `'[HEAD~1...HEAD]'`,
  `'[v1.0.0...v2.0.0]'`. `'[main]'` is shorthand for `'[main...HEAD]'`.
- **`--filter-affected`** is the convenience shorthand: it auto-detects the repo's default
  branch and diffs it against `HEAD` (≈ `--filter '[main...HEAD]'`).
- **Detection:** Terragrunt builds a git worktree per ref and diffs them. A unit matches if
  files in its directory are **Added/Modified** (seen in the "to" worktree) or **Removed**
  (seen in the "from" worktree).
- **Reads outside the unit count too:** if a unit `reading=` a shared file (or via
  `mark_glob_as_read()`) and that file changed, the unit is treated as affected — so a tweak
  to a shared `_env/region.hcl` correctly re-plans its consumers, not just the file's folder.
- **Local module files now count (v1.1.0):** when a unit's `terraform` `source` is a local
  directory, Terragrunt records that module's `*.tf`, `*.tf.json`, `*.hcl`, `*.tofu`,
  `*.tofu.json` files as read, so changing a local module selects its units via `reading=` /
  `--queue-include-units-reading`. GA (was `--experiment mark-many-as-read`); expect existing
  pipelines to select *more* units than before. The new `mark_glob_as_read()` HCL function
  marks additional files in one call (see references/functions.md).
- **Destroy safeguard:** git filters will **not** destroy units removed between the two refs
  unless you add **`--filter-allow-destroy`**. This prevents an accidental teardown when a
  unit directory is deleted in a PR.
- **Use remote state.** Git filters strongly assume remote state; with local state,
  dependency outputs may not resolve and mocks can silently substitute for real values.

Docs: https://docs.terragrunt.com/features/filter/git/

## Expand the changed set to dependents/dependencies (graph operators)

A changed module usually needs its **dependents** re-planned too. Graph operators walk the
DAG; the `...` position sets direction:

- `target...` — target **and everything it depends on** (its dependencies/ancestors).
- `...target` — target **and everything that depends on it** (its dependents/descendants) ← the one you want for "don't ship a change without its downstream".
- `...target...` — both directions.
- `^` — exclude the target itself, keep the related set (`...^vpc` = vpc's dependents, not vpc).
- depth limits: `service...1` (1 level of deps), `1...vpc` (direct dependents), applied per target.

**Combine git + graph for CI.** Union multiple `--filter` flags (repeating the flag is OR):
```bash
# changed units, plus their downstream dependents:
terragrunt run --all --filter '[main...HEAD]' --filter '...[main...HEAD]' -- plan
```
If a single combined expression (`'[main...HEAD]...'`) isn't accepted by your version, the
two-flag union above is the documented, safe form. For a destroy run you want the **reverse**
(dependents before dependencies) — Terragrunt handles ordering automatically; just include
the right set.

Docs: https://docs.terragrunt.com/features/filter/graph/ · https://docs.terragrunt.com/features/filter/

## Discover affected units for a CI matrix (`find` / `list`)

For self-hosted CI fan-out (e.g. a GitHub Actions matrix of one job per affected unit), use
`terragrunt find` — it's the JSON-friendly discovery command:

```bash
terragrunt find --json --filter-affected                 # affected units/stacks as JSON
terragrunt find --json --filter-affected --dependencies  # + dependency edges
terragrunt find --json --dependencies --dag              # dependency-sorted
terragrunt find --json --queue-construct-as=plan         # ordered as a plan would run
```
- `--json` → array of `{"type":"unit|stack","path":"..."}`; with `--dependencies` each entry
  gains a `"dependencies": [...]` list; `--reading` adds the files each unit reads.
- `--dag` sorts by dependency order; `--queue-construct-as` (alias `--as`) orders *as if* a
  given command ran (implies `--dag`) — `plan` puts dependents after dependencies, `destroy`
  before.
- `terragrunt list` is the human/visual sibling (`--format text|long|tree|dot`, `-l`, `-T`,
  DOT for GraphViz) — use `find --json` for machines, `list` for eyeballing the graph.

Feed the JSON to your matrix, then run each unit directly (`cd <path> && terragrunt apply`)
or run the whole affected set with `run --all --filter-affected`.

Docs: https://docs.terragrunt.com/reference/cli/commands/find/ · https://docs.terragrunt.com/reference/cli/commands/list/

## Speed knob 1: Provider Cache Server (download each provider once)

On a big `run --all`, every unit otherwise re-downloads providers. The provider cache server
downloads/stores each provider exactly once across all units.

- Enable: `--provider-cache` flag, or `TG_PROVIDER_CACHE=1`. Tune with `--provider-cache-dir`,
  `--provider-cache-registry-names`.
- **Require v1.1.2+ if the cache server can reach a private registry.** Before v1.1.2 the
  endpoint that downloads provider archives was the only one on the cache server that did
  not require the token generated for the run — and that endpoint attaches whatever registry
  credentials are configured for the upstream host. Any other process on the same machine
  could therefore drive a running cache server to pull artifacts from a private registry
  using the credentials of whoever started the run. This matters most where the blast radius
  is largest: a shared CI runner, or a workstation running anything untrusted. v1.1.2 puts a
  secret path segment (regenerated per server start, redacted from the server's own logs)
  into the URLs handed to OpenTofu/Terraform; requests without it get a 404. No config change
  is needed — the fix is the upgrade.
- **Require v1.1.3+ for two race conditions in the same area.** Both are correctness bugs
  rather than security ones, and both bite exactly where the cache server is most useful:
  - The server could begin answering requests before it had finished preparing the
    directories it caches into. A provider requested in that window had its archive and lock
    file written **relative to the working directory**, leaving zip files loose in the
    project tree. Providers now always download into the cache directory.
  - Two Terragrunt runs on one machine staged provider downloads at the same path, so the
    run that finished first could delete an archive the other was still unpacking, failing it
    with `failed to open zip archive`. Two runs can now cache the same provider concurrently.
    This is the one to quote at anyone running a parallel CI matrix on a shared runner.
- **`providers lock` flag values, v1.1.3+.** The space-delimited form
  (`providers lock -platform linux_amd64`) previously had its value moved to the end of the
  command, where it was read as a provider address and failed with
  `Invalid provider type "linux_amd64"`; only the attached form `-platform=linux_amd64`
  worked. `-fs-mirror` and `-net-mirror` were moved the same way. All now keep their values,
  and with `--provider-cache` enabled platforms are split correctly across the per-platform
  `providers lock` runs used to warm the cache.
- **Do NOT set `TF_PLUGIN_CACHE_DIR` yourself with `run --all`** — OpenTofu/Terraform's
  built-in plugin cache is not concurrency-safe, and parallel units corrupt it
  (`Error: Failed to install provider`). Let Terragrunt manage caching. On OpenTofu ≥ 1.10,
  Terragrunt's *Automatic Provider Cache Dir* configures this for you by default.
- Caveat: for a *single* `terragrunt plan` (not `--all`), the cache server can be a net
  negative — it's a large-fan-out optimization.

Docs: https://docs.terragrunt.com/features/provider-cache-server/ · https://docs.terragrunt.com/troubleshooting/performance/

## Speed knob 2: CAS — content-addressable source store

CAS avoids re-downloading remote module/catalog sources across many units/stacks (a cheap
per-getter probe — e.g. `git ls-remote` — yields a cache key without downloading; identical
files are hard-linked once). It speeds up catalog cloning, OpenTofu/Terraform source fetching,
and stack generation.

- **GA and on by default since v1.1.0** (was `--experiment cas`; the flag now just warns).
  Disable per run with `--no-cas` (env `TG_NO_CAS`). `--cas-clone-depth` (default 1; `-1` =
  full history). Available on `run`, `stack generate`, `stack run`, and `catalog`.
- **No longer Git-only** (v1.1.0): also deduplicates HTTP/HTTPS, Amazon S3, Google Cloud
  Storage, Mercurial, SMB, and OpenTofu/Terraform registry (`tfr://`) sources.
- Caveat: hard-link falls back to copy across filesystems; only delete the CAS dir when idle.
- See also `update_source_with_cas` / `mutable` in references/hcl-blocks.md for self-contained,
  content-addressed stack generation.

Docs: https://docs.terragrunt.com/features/caching/cas/

## Speed knob 3: fetch dependency outputs from state

`--dependency-fetch-output-from-state` reads a dependency's outputs straight from the remote
state file instead of running `tofu output` (and skips initializing the dependency) — a big
win when units have many dependencies.

- **S3 backends only**; falls back to the normal path elsewhere.
- **Incompatible with OpenTofu state encryption.**
- Still experimental: `--experiment=dependency-fetch-output-from-state`.

Docs: https://docs.terragrunt.com/troubleshooting/performance/ · https://docs.terragrunt.com/reference/experiments/active

## Parallelism & queue control

- **`--parallelism N`** caps concurrent units (default: unlimited). Tuning guidance: start at
  ~the number of CPU cores, then halve/double while measuring wall-clock. Set it **below** the
  isolated optimum when many units hammer the same shared API/backend (rate limits).
- **`--queue-ignore-dag-order`** runs units without DAG ordering — only safe for independent,
  read-only ops (e.g. `validate`); **dangerous for apply** (dependencies won't be ordered).
- **`--queue-ignore-errors`** keeps going after a unit fails — handy to collect *all* plan
  diffs in one CI pass; risky for apply.
- The **runner pool** schedules units as soon as their dependencies finish (no longer
  experimental) — you mostly just tune `--parallelism`.

Docs: https://docs.terragrunt.com/features/run-queue/ · https://docs.terragrunt.com/troubleshooting/performance/

## Trim per-unit overhead

- **Auto-init** runs `init` only when needed (source/state changed, first run, etc.). Leave
  it on; `--no-auto-init` (`TG_NO_AUTO_INIT=true`) skips it but then you must init yourself —
  use only when you've pre-initialized.
- **Keep dependency optimization on.** It's the default; `disable_dependency_optimization =
  true` is the *opt-out* and makes runs slower (it forces recursive dependency retrieval even
  when a unit doesn't read dependency outputs). Don't set it unless you have a reason.
- **Expensive discovery auth:** `--no-discovery-auth-provider-cmd`
  (`TG_NO_DISCOVERY_AUTH_PROVIDER_CMD`) skips per-unit `--auth-provider-cmd` runs during
  discovery when they dominate wall-clock. **GA since v1.1.0** — no longer needs
  `--experiment opt-out-auth`. Only safe when parsing resolves without credentials (a unit
  using e.g. `get_aws_account_id()` at parse time will fail with it set). For a costly shared
  command, wrap it in `run_cmd("--terragrunt-global-cache", ...)` so it runs once per invocation.
- **Validate-only CI without touching a backend:** pass `-backend=false` to OpenTofu via
  `extra_arguments` (note: `remote_state.disable_init` now passes `-backend-config` and
  requires the backend to exist — it is not the same as `-backend=false`). Backend
  bootstrapping is opt-in (`--backend-bootstrap` / `TG_BACKEND_BOOTSTRAP`, default off).

Docs: https://docs.terragrunt.com/features/auto-init/ · https://docs.terragrunt.com/troubleshooting/performance/

## CI output, exit codes & run reports

- **`--log-format json`** (also `pretty`/`bare`/`key-value`) for machine-parseable logs;
  `--non-interactive` (assume yes), `--no-color`.
- **Plan-diff detection:** pass tofu's detailed exit code after `--`:
  `terragrunt run --all plan -- -detailed-exitcode` → 0 none, 1 error, 2 changes. Terragrunt
  aggregates: any `1` ⇒ overall `1`; any `2` with no `1` ⇒ overall `2`. Great for "did
  anything change?" gates across hundreds of units.
- **Run report:** `--report-file` / `--report-format` (csv|json) summarizes per-unit results
  of an `--all` run — useful as a CI artifact.

Docs: https://docs.terragrunt.com/reference/logging/formatting/ · https://docs.terragrunt.com/reference/cli/commands/run/ · https://docs.terragrunt.com/features/stacks/run-report/

## What's OSS vs the paid Terragrunt Scale platform

Everything above is **free OSS CLI**: `--filter`/`--filter-affected` git+graph targeting,
`find`/`list` JSON discovery for CI matrices, the provider cache server, CAS,
`--dependency-fetch-output-from-state`, parallelism/queue control, the runner pool, and
detailed exit codes. A self-hosted pipeline of `terragrunt find --json --filter-affected`
(+ graph expansion) → matrix → `run --all` with the provider cache + CAS reproduces
*targeted, dependency-aware, cached* runs for free.

**Terragrunt Scale** (https://terragrunt.com/terragrunt-scale) is a managed product layered
on the CLI — hosted GitOps pipeline (plan-on-PR / apply-on-merge), scheduled drift detection
with auto-remediation PRs, dependency-update PRs (Patcher), and environment-segmented RBAC.
It adds *hosted orchestration and governance*, not new targeting primitives — so the
performance techniques here don't require it.

## Sources
- Filter (git/graph/file): https://docs.terragrunt.com/features/filter/
- find / list: https://docs.terragrunt.com/reference/cli/commands/find/ · .../list/
- run queue & parallelism: https://docs.terragrunt.com/features/run-queue/
- performance troubleshooting: https://docs.terragrunt.com/troubleshooting/performance/
- provider cache server: https://docs.terragrunt.com/features/provider-cache-server/
- CAS: https://docs.terragrunt.com/features/caching/cas/
- experiments — cas / mark-many-as-read / opt-out-auth / dag-queue-display / stack-dependencies / catalog-redesign graduated to GA in v1.1.0. Twelve active as of v1.1.2: azure-backend, deep-merge, dependency-fetch-output-from-state, hook-context-env, iac-engine, oci, optional-hooks, otel-logs, profiling, slow-task-reporting, symlinks, version-attribute (oci and version-attribute new in v1.1.1; otel-logs and profiling new in v1.1.2, and v1.1.2 also made azure-backend functional — see azure-backend.md). Authoritative list: https://docs.terragrunt.com/reference/experiments/active
- v1.1.0 release notes: https://github.com/gruntwork-io/terragrunt/releases/tag/v1.1.0
- v1.1.1 release notes: https://github.com/gruntwork-io/terragrunt/releases/tag/v1.1.1
- v1.1.3 release notes: https://github.com/gruntwork-io/terragrunt/releases/tag/v1.1.3 — two provider-cache race conditions fixed; `providers lock` space-delimited flag values; `--filter` now reserves `(`/`)` unconditionally and applies positive expressions after a leading negation; `tflint` hook honours `--config=`; `scaffold` fixed for units and stacks; five experiments added, none graduated
- v1.1.2 release notes: https://github.com/gruntwork-io/terragrunt/releases/tag/v1.1.2 — provider cache server download endpoint now requires the run's secret path segment; `find_in_parent_folders()` 7–10x faster; local-source hashing honours `include_in_copy`/`exclude_from_copy` so uncopied files no longer force a re-init
- run command flags & exit codes: https://docs.terragrunt.com/reference/cli/commands/run/
