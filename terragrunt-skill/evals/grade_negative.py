#!/usr/bin/env python3
"""Grade the NEGATIVE cases: does the skill emit Terragrunt config where none was asked for?

WHY A SECOND SUITE. `grade.py` measures compliance — given a Terragrunt task, does the answer
avoid pre-1.0 forms. A suite made only of positive cases measures EAGERNESS AS IF IT WERE
ACCURACY: a skill that answered every question with Terragrunt scaffolding would score
perfectly on it. These five cases are the other half.

THE LINE BETWEEN CORRECT AND OVER-REACH, and it is not "did the word Terragrunt appear".
Case 10 asks outright whether to adopt Terragrunt; discussing it is the whole job, and
answering "not for a 200-line single-environment config" is the RIGHT answer and mentions
Terragrunt throughout. So:

    Terragrunt constructs in PROSE      -> fine. Explaining, comparing, recommending against.
    Terragrunt constructs in a CODE BLOCK -> over-reach. Unasked-for scaffolding.

That is the signal this grades. It is deliberately narrow and it is mechanical.

WHAT IT CANNOT SEE. Whether the ADVICE is right. Case 10's correct answer is probably "no, not
yet" — a well-argued "yes" would be wrong and would score clean here, because it emitted no
config. Case 12's correct answer names `import`. Both need a human to read. This grades the
one thing that can be graded without a judge, and says so rather than implying more.

Usage:
    uv run evals/grade_negative.py
    uv run evals/grade_negative.py --show     # print the offending block for every hit
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import defaultdict

HERE = pathlib.Path(__file__).parent
RUNS = HERE / "runs"

NEGATIVE_CASES = ("8", "9", "10", "11", "12")

WHY = {
    "8":  "asks for a Terraform MODULE; the answer is .tf files, not a unit",
    "9":  "Kubernetes; nothing to do with Terragrunt at all",
    "10": "asks IF Terragrunt is warranted — discussing it is right, scaffolding it is not",
    "11": "generic HCL language question",
    "12": "asks for the import command; wrapping it in Terragrunt is unasked-for",
}

# Constructs that exist ONLY in Terragrunt config. Deliberately excludes a bare `terraform {`,
# which is a legitimate Terraform settings block and appears correctly in case 8.
CONSTRUCTS = (
    ("include block",        re.compile(r'include\s+"[^"]*"\s*\{|include\s*\{')),
    ("remote_state block",   re.compile(r"remote_state\s*\{")),
    ("dependency block",     re.compile(r'dependency\s+"[^"]*"\s*\{|dependencies\s*\{')),
    ("generate block",       re.compile(r'generate\s+"[^"]*"\s*\{')),
    # `source` must be a DIRECT child of the terraform block: no `{` may open between them.
    # With `[^}]*` this matched Terraform's own settings block, because
    # `required_providers { aws = { source = "hashicorp/aws" } }` puts a `source` inside a
    # nested block — and that is CORRECT Terraform, appearing legitimately in case 8. Excluding
    # `{` from the gap separates the two. It costs a false negative when someone writes
    # `extra_arguments` above `source` inside a Terragrunt terraform block; that ordering is
    # unusual, and a missed hit is far safer here than wrongly accusing a correct answer.
    ("terraform.source",     re.compile(r"terraform\s*\{[^{}]*\bsource\s*=", re.S)),
    ("unit/stack block",     re.compile(r'unit\s+"[^"]*"\s*\{|stack\s+"[^"]*"\s*\{')),
    ("find_in_parent_folders", re.compile(r"find_in_parent_folders\s*\(")),
    ("path_relative_*",      re.compile(r"path_relative_(to|from)_include\s*\(")),
    ("run --all",            re.compile(r"\brun\s+--all\b")),
)

FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.S)


def result_text(p: pathlib.Path) -> str:
    try:
        raw = p.read_text()
    except OSError:
        return ""
    try:
        env = json.loads(raw)
    except json.JSONDecodeError:
        try:
            env, _ = json.JSONDecoder().raw_decode(raw, 0)
        except json.JSONDecodeError:
            print(f"  DAMAGED {p.name}: no complete JSON envelope; excluded")
            return ""
        print(f"  DAMAGED {p.name}: trailing bytes (concurrent writers). Using the first envelope.")
    t = env.get("result")
    return t if isinstance(t, str) else ""


def overreach(text: str) -> list[tuple[str, str]]:
    """Constructs found INSIDE fenced code blocks. Prose mentions are not counted."""
    found = []
    for block in FENCE.findall(text):
        for name, pattern in CONSTRUCTS:
            m = pattern.search(block)
            if m:
                found.append((name, block.strip()[:400]))
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    ap.add_argument("--show", action="store_true", help="print the offending block for every hit")
    args = ap.parse_args()

    files = sorted(RUNS.glob("*.json"))
    if not files:
        print(f"No runs in {RUNS}. Run: CASES=\"8 9 10 11 12\" ./evals/matrix.sh", file=sys.stderr)
        return 1

    per_arm = defaultdict(lambda: [0, 0])          # arm -> [runs, runs with over-reach]
    per_cell = defaultdict(list)                    # (case, arm) -> [n per replicate]
    detail = []
    seen = 0
    for p in files:
        m = re.fullmatch(r"(\d+)-([CSP])-(\d+)", p.stem)
        if not m or m.group(1) not in NEGATIVE_CASES:
            continue
        case, arm, rep = m.groups()
        text = result_text(p)
        if not text:
            continue
        seen += 1
        hits = overreach(text)
        per_arm[arm][0] += 1
        if hits:
            per_arm[arm][1] += 1
            detail.append((case, arm, rep, hits))
        per_cell[(case, arm)].append(len(hits))

    if not seen:
        print(f"No negative-case runs found. Run: CASES=\"{' '.join(NEGATIVE_CASES)}\" ./evals/matrix.sh",
              file=sys.stderr)
        return 1

    print()
    print("UNASKED-FOR TERRAGRUNT CONFIG, BY ARM")
    print("  A hit is a Terragrunt construct inside a CODE BLOCK. Prose mentions are correct.")
    print()
    print(f"  {'arm':<5}{'runs':>6}{'runs w/ over-reach':>21}{'rate':>8}")
    for arm in ("C", "S", "P"):
        runs, bad = per_arm.get(arm, [0, 0])
        if runs:
            print(f"  {arm:<5}{runs:>6}{bad:>21}{bad / runs:>8.0%}")

    print()
    print("BY CASE (constructs found, summed over replicates)")
    print(f"  {'case':<6}{'C':>4}{'S':>4}{'P':>4}   why this case is a negative")
    for c in NEGATIVE_CASES:
        row = "".join(f"{sum(per_cell.get((c, a), [])):>4}" for a in ("C", "S", "P"))
        print(f"  {c:<6}{row}   {WHY[c]}")

    if args.show and detail:
        print()
        for case, arm, rep, hits in detail:
            print("=" * 74)
            print(f"case {case} arm {arm} rep {rep} — {', '.join(sorted({h[0] for h in hits}))}")
            print("-" * 74)
            print(hits[0][1])

    # SECOND SIGNAL. The over-reach measure came back null on every arm on 2026-08-19 -- the
    # model does not emit unasked-for scaffolding even WITHOUT the skill, so these cases cannot
    # separate the arms on that axis. But the same runs carry a different signal: when the model
    # merely DISCUSSES Terragrunt, does it use the current vocabulary? Case 10 asks whether to
    # adopt it, so a name gets used with no config requested at all. Reuse grade.py's detection.
    import importlib.util
    spec = importlib.util.spec_from_file_location("g", HERE / "grade.py")
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)

    term = defaultdict(lambda: [0, 0])
    for p2 in files:
        m = re.fullmatch(r"(\d+)-([CSP])-(\d+)", p2.stem)
        if not m or m.group(1) not in NEGATIVE_CASES:
            continue
        case, arm, rep = m.groups()
        text = result_text(p2)
        if not text:
            continue
        term[arm][0] += 1
        if any(h["auto"] == "violation" for h in g.find_hits(text, case, arm, rep)):
            term[arm][1] += 1

    print()
    print("PRE-1.0 VOCABULARY WHILE MERELY DISCUSSING TERRAGRUNT")
    print("  No config was requested in any of these cases. This is what the model CALLS things.")
    print()
    print(f"  {'arm':<5}{'runs':>6}{'runs w/ a pre-1.0 name':>25}")
    for arm in ("C", "S", "P"):
        runs, bad = term.get(arm, [0, 0])
        if runs:
            print(f"  {arm:<5}{runs:>6}{bad:>25}")
    print("  (auto-classified; adjudicated 2026-08-19 as C=3 S=0 P=1 -- see RESULTS.md)")

    print()
    print("  NOT GRADED HERE: whether the ADVICE is right. Case 10's correct answer is probably")
    print("  'not yet'; a confident 'yes' would be wrong and would still score clean, because it")
    print("  emitted no config. Read those by hand.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
