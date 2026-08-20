#!/usr/bin/env python3
"""Scan this skill's own files for the pre-1.0 Terragrunt forms its hard policy bans.

WHY THIS EXISTS. Terragrunt v1.0.0 (2026-03-30) renamed much of the CLI. SKILL.md's first hard
policy bans the old forms. But five of the nine reference files declare in their own headers
that they were "harvested from omattsson/terragrunt-mcp-server" -- a repository whose last
commit is 2026-02-22, five weeks BEFORE v1.0.0 existed. The ban was written afterwards and
nothing reconciled the two.

Two defects had already been found by hand when this was written:
  hcl-blocks.md      three pre-1.0 retry blocks documented as current, no `errors` block at all
  best-practices.md  a plan/apply pipeline using `-out=tfplan` across a stack, and no `--`

Both were found by accident, while doing something else. This makes the check repeatable.

WHAT COUNTS AS A HIT. Naming an obsolete form in order to WARN about it is correct and common
in this skill -- the hard policy itself lists every one of them. So a match is only reported
when nothing nearby marks it as obsolete. That is a heuristic, not a proof: read every hit.

Usage:
    uv run scripts/scan_pre10.py              # report, exit 1 if any unmarked hit
    uv run scripts/scan_pre10.py --all        # show marked hits too
    uv run scripts/scan_pre10.py --path FILE  # one file
"""

from __future__ import annotations

import argparse
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent

# The forms hard-policy item 1 bans, plus the two retry siblings found alongside
# `retryable_errors`. `skip` and `find_in_parent_folders` need shape, not just the word.
FORMS: tuple[tuple[str, str, str], ...] = (
    ("run-all",                  r"\brun-all\b",                    "run --all"),
    ("plan-all",                 r"\bplan-all\b",                   "run --all -- plan"),
    ("apply-all",                r"\bapply-all\b",                  "run --all -- apply"),
    ("destroy-all",              r"\bdestroy-all\b",                "run --all -- destroy"),
    ("output-all",               r"\boutput-all\b",                 "run --all -- output"),
    ("validate-all",             r"\bvalidate-all\b",               "run --all -- validate"),
    ("hclfmt",                   r"\bhclfmt\b",                     "hcl fmt"),
    ("hclvalidate",              r"\bhclvalidate\b",                "hcl validate"),
    ("graph-dependencies",       r"\bgraph-dependencies\b",         "dag graph"),
    ("validate-inputs",          r"\bvalidate-inputs\b",            "hcl validate --inputs"),
    ("--terragrunt-flag",        r"--terragrunt-[a-z][a-z0-9-]*",   "the same flag, no prefix"),
    ("skip-attribute",           r"^\s*skip\s*=\s*(?:true|false)",  "an exclude block"),
    ("retryable_errors",         r"\bretryable_errors\b",           "errors { retry {} }"),
    ("retry_max_attempts",       r"\bretry_max_attempts\b",         "errors { retry { max_attempts } }"),
    ("retry_sleep_interval_sec", r"\bretry_sleep_interval_sec\b",   "errors { retry { sleep_interval_sec } }"),
    ("bare-fipf",                r"find_in_parent_folders\(\s*\)",  'find_in_parent_folders("root.hcl")'),
)

# Nearby text that marks a mention as deliberate rather than taught-as-current.
MARKED = re.compile(
    r"pre-1\.0|before 1\.0|0\.x|deprecat|obsolete|no longer|removed in|renamed|superseded|"
    r"legacy|never (generate|recommend|emit|use)|do not (use|emit)|don't use|"
    r"replaces|replaced|instead of|rather than|flag (them|it)|the old\b|used to be",
    re.I,
)

# Two HCL FUNCTIONS keep the `--terragrunt-` prefix on their special leading arguments. Those
# were never CLI flags, so the 1.0 CLI rename did not touch them. Verified against
# docs.terragrunt.com/reference/hcl/functions/ on 2026-08-19, which still shows
# `run_cmd("--terragrunt-quiet", "./decrypt_secret.sh", "foo")` and
# `mark_glob_as_read("--terragrunt-boundary=/etc/terragrunt", ...)`.
# Ten hits in functions.md and one in scale-and-performance.md were false positives on the
# first run because of this. Every false positive found by hand becomes a rule here.
# Section-aware rather than a proximity window: a `## FUNCTION: run_cmd` section documents its
# flags several lines below the heading, and a window wide enough to catch them would start
# swallowing the neighbouring function's examples.
PREFIX_FUNCTIONS = ("run_cmd", "mark_glob_as_read")
SECTION = re.compile(r"^#+\s*(?:FUNCTION:\s*)?(\w+)")

# A banned name inside a FILENAME is not a Terragrunt command --- `./scripts/validate-inputs.sh`
# is a user's own script. advanced-examples.md:1074 was a false positive for this reason.
FILENAME = re.compile(r"[/\w-]*(?:\.sh|\.py|\.ps1|\.bash)\b")

# `retryable_errors` is BANNED at top level and VALID inside the 1.x errors block.
LEGAL_INSIDE = {
    "retryable_errors":         re.compile(r"errors\s*\{|retry\s+\"|retry\s*\{"),
    "retry_max_attempts":       re.compile(r"errors\s*\{|retry\s+\"|retry\s*\{"),
    "retry_sleep_interval_sec": re.compile(r"errors\s*\{|retry\s+\"|retry\s*\{"),
}

WINDOW = 2      # lines either side searched for a MARKED signal
ENCLOSING = 12  # lines searched BACKWARDS for an allowing block

# scripts/ was OUTSIDE this scan until 2026-08-20, and that is how validate.sh -- the skill's
# own executable validator -- kept gating on Terragrunt 0.93 while the skill it ships with
# bans every pre-1.0 form. Prose is not the only place a stale form hides; something that RUNS
# is worse, because it acts on the claim.
TARGETS = ["SKILL.md", "README.md"] + sorted(
    str(p.relative_to(ROOT)) for p in (ROOT / "references").glob("*.md")
) + sorted(str(p.relative_to(ROOT)) for p in (ROOT / "templates").rglob("*.hcl")) + sorted(
    str(p.relative_to(ROOT)) for p in (ROOT / "scripts").iterdir()
    if p.suffix in (".sh", ".py") and p.name != "scan_pre10.py"
)

# Files harvested from the pre-1.0 source, per their own headers. Reported separately because
# they are where a hit is most likely and least surprising.
HARVESTED = {
    "references/advanced-examples.md", "references/best-practices.md",
    "references/error-patterns.md", "references/functions.md", "references/hcl-blocks.md",
}


def scan(path: pathlib.Path, rel: str) -> list[dict]:
    lines = path.read_text().splitlines()
    out = []
    section = ""
    for i, line in enumerate(lines):
        head = SECTION.match(line)
        if head:
            section = head.group(1)
        for form, pattern, replacement in FORMS:
            for m in re.finditer(pattern, line, re.M):
                near = "\n".join(lines[max(0, i - WINDOW):i + WINDOW + 1])
                back = "\n".join(lines[max(0, i - ENCLOSING):i])
                legal = LEGAL_INSIDE.get(form)
                in_filename = any(
                    fm.start() <= m.start() and m.end() <= fm.end()
                    for fm in FILENAME.finditer(line)
                )
                if form == "--terragrunt-flag" and (
                    section in PREFIX_FUNCTIONS
                    or any(fn in line for fn in PREFIX_FUNCTIONS)
                ):
                    state = "function-arg"
                elif in_filename:
                    state = "filename"
                elif legal and legal.search(back):
                    state = "valid-1x"
                elif MARKED.search(near):
                    state = "marked"
                else:
                    state = "UNMARKED"
                out.append({
                    "file": rel, "line": i + 1, "form": form, "matched": m.group(0),
                    "should_be": replacement, "state": state, "text": line.strip()[:110],
                })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    ap.add_argument("--all", action="store_true", help="show marked and valid-1x hits too")
    ap.add_argument("--path", help="scan one file instead of the whole skill")
    args = ap.parse_args()

    targets = [args.path] if args.path else TARGETS
    hits: list[dict] = []
    for rel in targets:
        p = ROOT / rel
        if p.exists():
            hits.extend(scan(p, rel))

    unmarked = [h for h in hits if h["state"] == "UNMARKED"]
    shown = hits if args.all else unmarked

    by_file: dict[str, list[dict]] = {}
    for h in shown:
        by_file.setdefault(h["file"], []).append(h)

    for rel in sorted(by_file):
        tag = "  [harvested from the pre-1.0 source]" if rel in HARVESTED else ""
        print(f"\n{rel}{tag}")
        for h in by_file[rel]:
            flag = "" if h["state"] == "UNMARKED" else f"  ({h['state']})"
            print(f"  {h['line']:>5}  {h['form']:<24} -> {h['should_be']}{flag}")
            print(f"         {h['text']}")

    print()
    print(f"scanned {len(targets)} files")
    print(f"  {len(hits):>4} mentions of a banned form")
    print(f"  {sum(1 for h in hits if h['state'] == 'marked'):>4} marked as obsolete (correct)")
    print(f"  {sum(1 for h in hits if h['state'] == 'valid-1x'):>4} valid 1.x usage inside an allowing block")
    n_fn = sum(1 for h in hits if h["state"] == "function-arg")
    print(f"  {n_fn:>4} HCL function args that keep the prefix (run_cmd, mark_glob_as_read)")
    print(f"  {sum(1 for h in hits if h['state'] == 'filename'):>4} inside a filename, not a command")
    print(f"  {len(unmarked):>4} UNMARKED -- taught as current")
    if unmarked:
        h_files = sorted({h["file"] for h in unmarked if h["file"] in HARVESTED})
        if h_files:
            print(f"\n  of which, in harvested files: {', '.join(h_files)}")
        print("\n  Read every one. The heuristic cannot tell a worked example that happens to")
        print("  quote old output from one that teaches the old form.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
