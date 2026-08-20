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
)

# Changes that break a working configuration on upgrade WITHOUT anyone enabling anything.
# This is the column a version number cannot give you, and the reason this file is not just
# a comparison. Keyed by the version you are crossing INTO; the second element is the version
# that FIXED it, or None if it is permanent. A hazard that was later fixed must stop being
# reported once you are past the fix, or the report cries wolf and stops being read.
HAZARDS = {
    "1.1.1": ("1.1.2", (
        "iam_role / --iam-assume-role with static AWS credentials assumed the role twice "
        "and failed with AccessDenied. The error points at the trust policy; editing the "
        "trust policy is the wrong fix. Fixed in 1.1.2 -- do not sit on 1.1.1.",
    )),
    "1.1.3": (None, (
        "--filter now reserves ( and ) for the bounded-discovery boundary operand, and the "
        "reservation applies whether or not the experiment is enabled. "
        "--filter '1...(foo | bar)' is now rejected as a malformed boundary. Wrap names or "
        "paths containing parentheses in braces: --filter '{./weird(name)}'. "
        "Audit filter strings and unit names for parentheses before upgrading.",
        "A --filter query beginning with a negation used to be treated as wholly "
        "exclusionary, so positive expressions after it did not restrict the selection. "
        "They now do, which changes what existing queries return.",
    )),
}

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
        run = lambda: subprocess.run(  # noqa: E731
            ["terragrunt", "--version"], capture_output=True, text=True, timeout=20, check=False
        )
    try:
        proc = run()
    except (OSError, subprocess.SubprocessError) as e:
        return "", f"could not run terragrunt --version: {type(e).__name__}"
    if proc.returncode != 0:
        return proc.stdout or "", f"terragrunt --version exited {proc.returncode}"
    return (proc.stdout or "").strip(), None


def gates_for(installed: tuple[int, int, int]) -> tuple[list, list]:
    """(satisfied, unmet) gate rows for an installed version."""
    satisfied, unmet = [], []
    for ver, kind, items in GATES:
        (satisfied if installed >= parse(ver) else unmet).append((ver, kind, items))
    return satisfied, unmet


def hazards_for(installed: tuple[int, int, int]) -> list[str]:
    """Hazards in effect on this build, newest first.

    In effect means introduced at or below the installed version AND not yet fixed by it.
    A hazard that has been fixed is not a hazard, and reporting it anyway is how a report
    trains people to skim past the ones that matter.
    """
    out = []
    for ver in sorted(HAZARDS, key=parse, reverse=True):
        fixed_in, texts = HAZARDS[ver]
        if installed < parse(ver):
            continue
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

    shown = ".".join(str(n) for n in got)
    newest = parse(GATES[-1][0])
    lines = [f"terragrunt {shown}"]

    satisfied, unmet = gates_for(got)
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
