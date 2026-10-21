#!/usr/bin/env python3
"""Read the installed Terragrunt and report which of this skill's gates it satisfies.

WHY THIS EXISTS. Until 2026-08-19 SKILL.md opened by asserting "current stable v1.1.2".
That claim was wrong within a fortnight -- v1.1.3 shipped 2026-08-13 and the binary on the
author's own machine was already ahead of the sentence. A "current stable" line is a fact
with a half-life of about six weeks, and nothing in the repository notices when it expires.

So this skill no longer asserts what the current release is. It asserts what each FEATURE
requires, which is a fact about history and does not rot, and it asks the machine what is
actually installed. Those two together give the answer the prose was trying to give, and
they stay true without maintenance.

WHAT IT REPORTS. For the installed version: which gated features are safe to emit, which
must not be emitted, and any upgrade hazard that applies. The hazards are the expensive
part -- they are changes that break a working configuration without anyone opting in, and
a version number alone will not tell you about them.

WHAT IT DELIBERATELY DOES NOT DO.

  IT DOES NOT BLOCK. A check that fails the day Terragrunt ships a patch is a check that
  gets commented out. Drift warns and names what to re-read. `--strict` exists for CI.

  IT DOES NOT RUN TERRAGRUNT AGAINST ANY INFRASTRUCTURE. `terragrunt --version` touches no
  state, no cloud provider and no network.

  IT DOES NOT CLAIM THE GATE LIST IS COMPLETE. It covers the gates this skill's references
  actually depend on. An unfamiliar `--experiment` value is still a "go and read the docs".

Usage:
    python3 scripts/preflight.py
    python3 scripts/preflight.py --strict           # any hazard or unknown version fails
    python3 scripts/preflight.py --version 1.1.3    # report for a version without running it
"""

import argparse
import re
import shutil
import subprocess

# EVERY GATE THIS SKILL'S REFERENCES DEPEND ON, keyed by the version that introduced it.
# These are historical facts. Add a row when a release adds a gate; never rewrite a row,
# because "autoinclude arrived in 1.1.0" does not stop being true.
GATES = (
    ("1.1.0", "GA, no experiment needed", (
        "autoinclude block; unit.<name>.path / stack.<name>.path references",
        "dependency on a stack directory (via autoinclude)",
        "update_source_with_cas and mutable on the unit block",
        "CAS enabled by default (--experiment cas now only warns)",
    )),
    ("1.1.1", "opt-in experiment", (
        "terraform.source oci:// registries        --experiment oci",
        "terraform.version constraint for tfr://   --experiment version-attribute",
    )),
    ("1.1.2", "advice, not syntax", (
        "provider cache server requires the run's token (private-registry exposure)",
        "azure-backend went from inert to functional --experiment azure-backend",
    )),
    ("1.1.3", "advice and opt-in experiments", (
        "two provider-download race conditions fixed",
        "generate.mutable                          --experiment mutable-generate",
        "expansion block / unit.enabled RESERVED   --experiment block-iteration",
        "--discovery-boundary and (dir) operand    --experiment bounded-discovery",
        "--no-dependency-outputs                   --experiment optional-dependency-outputs",
        "terragrunt browse                         --experiment browse-tui",
    )),
    ("1.1.4", "opt-in strict control, and two CAS repairs", (
        "duplicate dependency labels warn by default; they are an ERROR under "
        "--strict-control duplicate-dependency-labels",
        "terragrunt scaffold opens the Catalog TUI form instead of writing # TODO",
        "git source ?depth= works again (broken 1.1.0-1.1.3)",
        "CAS reads an already-initialized local source again (broken 1.1.0-1.1.3)",
    )),
    ("1.1.5", "opt-in experiments, and a wider strict control", (
        "duplicate-dependency-labels also catches two labels sharing one config_path",
        "CAS records probe answers; --cas-offline, --cas-refresh, --cas-probe-ttl "
        "--experiment offline-cas",
        "base64gzip_compat() keeps the v1.1.3 bytes permanently "
        "--experiment base64gzip-compat",
        "base64gzip() returns the v1.1.3 bytes again (the v1.1.4 bytes planned replacements)",
    )),
    ("1.1.6", "advice, not syntax", (
        "Windows: find / list / browse with a Git filter find nested units again",
    )),
    ("1.2.0", "GA, eleven experiments completed -- their --experiment flags only warn", (
        "terraform.source / unit / stack source oci://  (was --experiment oci)",
        "terraform.version constraint for tfr://   (was --experiment version-attribute)",
        "expansion block (count / for_each) on unit, stack and dependency; unit.<name>[key].path; "
        "enabled on unit and stack  (was --experiment block-iteration, reserved-only before)",
        "--discovery-boundary and the (dir) filter operand  (was --experiment bounded-discovery)",
        "generate.mutable; generated files live in the CAS, read-only by default "
        "(was --experiment mutable-generate)",
        "--no-dependency-outputs  (was --experiment optional-dependency-outputs)",
        "--no-hooks  (was --experiment optional-hooks)",
        "--profile-cpu / --profile-mem / --profile-goroutine / --profile-dir  "
        "(was --experiment profiling)",
        "catalog --format=jsonl|md, and jsonl by default off a terminal  "
        "(was --experiment catalog-format)",
        "azurerm state bootstrap, delete and migrate; minimum_tls_version  "
        "(was --experiment azure-backend)",
        "dependency outputs read from S3 / GCS / azurerm state by default; "
        "--no-dependency-fetch-output-from-state forces output -json  "
        "(was --experiment dependency-fetch-output-from-state)",
        "OpenTofu 1.13 functions in Terragrunt HCL (assume*, templatestring, urldecode, ...)",
        "S3 enable_bucket_root_access = true; '-an' bucket names use the account regional namespace",
        "still EXPERIMENTAL: base64gzip_compat() (--experiment base64gzip-compat), "
        "terragrunt mcp (--experiment mcp-command, not stable before v1.3)",
    )),
)

# Changes that break a working configuration on upgrade WITHOUT anyone enabling anything.
# This is the column a version number cannot give you, and the reason this file is not just
# a comparison. Keyed by the version you are crossing INTO. Each version holds one or more
# (fixed_in, texts) groups -- fixed_in is the version that FIXED the group, or None if it is
# permanent. Groups, not a single pair, because v1.1.4 brought a permanent change and a
# later-fixed one in the same release. A hazard that was later fixed must stop being
# reported once you are past the fix, or the report cries wolf and stops being read.
HAZARDS = {
    "1.1.1": (("1.1.2", (
        "iam_role / --iam-assume-role with static AWS credentials assumed the role twice "
        "and failed with AccessDenied. The error points at the trust policy; editing the "
        "trust policy is the wrong fix. Fixed in 1.1.2 -- do not sit on 1.1.1.",
    )),),
    # Entered when CAS became the default path for git sources in 1.1.0, and both
    # went unnoticed for four releases. They are reported for anyone still on
    # 1.1.0-1.1.3, which is the whole point of keying hazards by the version you
    # cross INTO rather than by the version that fixed them.
    "1.1.0": (("1.1.4", (
        "A terraform.source (or stack source) URL carrying the go-getter depth query "
        "parameter -- ...vpc.git?depth=1&ref=v5.21.0 -- FAILS TO DOWNLOAD. CAS lifts ref "
        "out of the URL but left depth in place, so git receives ...vpc.git?depth=1 and "
        "rejects it as an invalid repository name. A depth with no ref fails the same way. "
        "Clone depth comes from --cas-clone-depth (default 1) and a depth on the URL is "
        "never applied to a CAS clone, so the parameter can simply be deleted. "
        "Fixed in 1.1.4.",
        "With CAS enabled, reading a LOCAL source that has already been initialized fails "
        "and silently falls back to the slower standard copy; generating a stack from such "
        "a unit logs 'CAS processing failed ... source escapes repository root'. The cause "
        "is provider caching -- both the Provider Cache Server and the Automatic Provider "
        "Cache Dir leave .terraform pointing outside the source, which CAS reads as the "
        "source escaping itself. Fixed in 1.1.4, which leaves .terraform and "
        ".terragrunt-cache out of local sources while keeping .terraform.lock.hcl.",
    )),),
    "1.1.3": ((None, (
        "--filter now reserves ( and ) for the bounded-discovery boundary operand, and the "
        "reservation applies whether or not the experiment is enabled. "
        "--filter '1...(foo | bar)' is now rejected as a malformed boundary. Wrap names or "
        "paths containing parentheses in braces: --filter '{./weird(name)}'. "
        "Audit filter strings and unit names for parentheses before upgrading.",
        "A --filter query beginning with a negation used to be treated as wholly "
        "exclusionary, so positive expressions after it did not restrict the selection. "
        "They now do, which changes what existing queries return.",
    )),),
    "1.1.4": ((None, (
        "When --tf-path (TG_TF_PATH) is NOT set, Terragrunt no longer runs 'tofu -version' "
        "to choose the binary it wraps. It now selects tofu whenever tofu is on PATH. On a "
        "machine where tofu is present but cannot run, Terragrunt used to fall back to "
        "terraform silently and now reports the failure instead. Set --tf-path or "
        "TG_TF_PATH explicitly if you were relying on that fallback.",
        "terragrunt scaffold is now INTERACTIVE from a terminal: it opens the Catalog TUI "
        "form and collects values instead of writing # TODO placeholders, and dismissing "
        "the form with esc writes NOTHING. The old behaviour still applies under "
        "--non-interactive, when stdin is not a terminal, or when the source asks for "
        "nothing -- so CI is unaffected, but a human following a scripted runbook, or an "
        "agent driving a PTY, will meet a form where a file used to appear.",
    )), ("1.1.5", (
        "base64gzip() returns DIFFERENT BYTES (v1.1.4 was built with Go 1.27). They decompress "
        "to the same value, but a resource comparing the encoded value -- an EC2 instance with "
        "user_data_base64 and user_data_replace_on_change = true -- plans a REPLACEMENT. "
        "Fixed in 1.1.5, which restores the v1.1.3 bytes. Do not apply a plan on 1.1.4 that "
        "replaces an instance for no reason you can name.",
    ))),
    "1.1.5": ((None, (
        "get_repo_root(), get_path_from_repo_root() and get_path_to_repo_root() no longer run "
        "git. They look for a .git entry themselves, so GIT_DIR, GIT_WORK_TREE and "
        "core.worktree are IGNORED and the safe.directory ownership check is not applied "
        "(GIT_CEILING_DIRECTORIES still works). A config relying on those settings resolves a "
        "different root.",
        "Files written by generate blocks are created 0600, not 0644. Anything that expected "
        "another user or group to read a generated file loses access.",
        "A current flag or env var name now beats its deprecated name at the same level: "
        "TG_LOG_LEVEL=info is no longer overridden by TERRAGRUNT_LOG_LEVEL=debug beside it. "
        "A CLI argument still beats an environment variable under either name.",
    )),),
    # Listed by Gruntwork as within the 1.0 guarantees, which is about the CLI and HCL
    # schemas. Each of these still changes a plan, a permission or a script's input.
    "1.2.0": ((None, (
        "PLAN-VISIBLE: base64gzip() returns the Go 1.27 bytes. A resource comparing the "
        "encoded value (aws_instance user_data_base64 with user_data_replace_on_change = true) "
        "plans a REPLACEMENT on the first run. base64gzip_compat() under "
        "--experiment base64gzip-compat keeps the v1.1.3 bytes.",
        "PLAN-VISIBLE: S3 state bucket bootstrap no longer adds the RootAccess statement "
        "(s3:* for the whole account). skip_bucket_root_access is deprecated; "
        "enable_bucket_root_access = true restores it. Existing buckets keep the statement.",
        "Generated files now live in the CAS and are READ-ONLY by default. A hook or script "
        "that edits provider.tf (or any generated file) in place fails with a permission "
        "error. Set mutable = true on that generate block, or run with --no-cas.",
        "--backend-bootstrap now CREATES the azurerm resource group, storage account and "
        "container it used to skip, and converges versioning and soft delete on existing "
        "accounts. New accounts get minimum TLS 1.2.",
        "terragrunt catalog writes jsonl instead of opening the TUI when stdin or stdout is "
        "not a terminal.",
        "terragrunt info print --all writes JSON Lines, and each unit's own download_dir. "
        "Anything parsing the old indented output breaks.",
        "hcl validate FAILS on a dependency whose config_path has no unit; a malformed "
        "exclude block (e.g. actions = \"plan\") is now an error instead of being dropped; "
        "a stack declaring one unit/stack label both with and without expansion fails to parse.",
        "plan/apply -destroy=true now counts as destroy: prevent_destroy stops it, and "
        "exclude, hook and extra_arguments rules for destroy apply.",
        "S3 access-log buckets Terragrunt creates get a bucket policy, not an ACL; "
        "skip_accesslogging_bucket_acl is deprecated and does nothing.",
    )),),
}

# A pre-release of a recorded version (v1.2.0-rc1) parses as that version but is not it: an
# rc lacks the fixes made before release. It must not satisfy its own version's gate.
PRERELEASE_RE = re.compile(r"\d+\.\d+\.\d+-[0-9A-Za-z]")

VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def parse(text: str) -> tuple[int, int, int] | None:
    """First x.y.z in whatever was printed. None rather than a guess."""
    m = VERSION_RE.search(text or "")
    return tuple(int(g) for g in m.groups()) if m else None


def read_version(run=None) -> tuple[str, str | None]:
    """(raw output, error). `run` is injectable so the tests never shell out."""
    if run is None:
        if not shutil.which("terragrunt"):
            return "", "terragrunt is not on PATH"
        def run():
            return subprocess.run(
                ["terragrunt", "--version"], capture_output=True, text=True, timeout=20, check=False
            )
    try:
        proc = run()
    except (OSError, subprocess.SubprocessError) as e:
        return "", f"could not run terragrunt --version: {type(e).__name__}"
    if proc.returncode != 0:
        return proc.stdout or "", f"terragrunt --version exited {proc.returncode}"
    return (proc.stdout or "").strip(), None


def gates_for(installed: tuple[int, int, int], pre: bool = False) -> tuple[list, list]:
    """(satisfied, unmet) gate rows for an installed version. A pre-release of a version
    does not satisfy that version's own gate."""
    satisfied, unmet = [], []
    for ver, kind, items in GATES:
        g = parse(ver)
        ok = installed > g or (installed == g and not pre)
        (satisfied if ok else unmet).append((ver, kind, items))
    return satisfied, unmet


def hazards_for(installed: tuple[int, int, int]) -> list[str]:
    """Hazards in effect on this build, newest first.

    In effect means introduced at or below the installed version AND not yet fixed by it.
    A hazard that has been fixed is not a hazard, and reporting it anyway is how a report
    trains people to skim past the ones that matter.
    """
    out = []
    for ver in sorted(HAZARDS, key=parse, reverse=True):
        if installed < parse(ver):
            continue
        for fixed_in, texts in HAZARDS[ver]:
            if fixed_in and installed >= parse(fixed_in):
                continue
            out += [f"{ver}: {h}" for h in texts]
    return out


def report(raw: str, err: str | None) -> tuple[int, list[str]]:
    """(exit code, lines). Exit 1 only when the check CANNOT be made."""
    if err:
        return 1, [f"FAIL {err}"]
    got = parse(raw)
    if not got:
        return 1, [f"FAIL could not parse a version out of {raw!r}"]

    pre = bool(PRERELEASE_RE.search(raw))
    shown = ".".join(str(n) for n in got)
    newest = parse(GATES[-1][0])
    lines = [f"terragrunt {shown}" + (" (PRE-RELEASE)" if pre else "")]
    if pre:
        lines.append(f"WARN  a pre-release of v{shown} does not reach the v{shown} gate; "
                     "upgrade to the release before emitting anything it graduates.")

    satisfied, unmet = gates_for(got, pre)
    if satisfied:
        lines.append("")
        lines.append("SAFE TO EMIT -- gates this build satisfies:")
        for ver, kind, items in satisfied:
            lines.append(f"  v{ver}+  ({kind})")
            lines += [f"      - {i}" for i in items]
    if unmet:
        lines.append("")
        lines.append("DO NOT EMIT -- gates this build does not reach:")
        for ver, kind, items in unmet:
            lines.append(f"  v{ver}+  ({kind})")
            lines += [f"      - {i}" for i in items]

    haz = hazards_for(got)
    if haz:
        lines.append("")
        lines.append("UPGRADE HAZARDS already in effect on this build:")
        lines += [f"  ! {h}" for h in haz]

    if got > newest:
        lines.append("")
        lines.append(
            f"WARN  this build is ahead of every gate this skill records (newest v{GATES[-1][0]}). "
            "Read the release notes in full before trusting the advice above -- "
            "a patch can reserve syntax without enabling anything."
        )
    return 0, lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on an unrecorded version as well as an unreadable one")
    ap.add_argument("--version", help="report for this version instead of running terragrunt")
    args = ap.parse_args(argv)

    raw, err = (args.version, None) if args.version else read_version()
    code, lines = report(raw, err)
    print("\n".join(lines))
    if args.strict and code == 0 and (got := parse(raw)) and got > parse(GATES[-1][0]):
        return 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
