#!/usr/bin/env python3
"""Build the three arms for the terragrunt-skill policy-compliance eval.

THE QUESTION. terragrunt-skill's first hard-policy rule bans every pre-1.0 CLI form:
`run-all`, `plan-all`, `hclfmt`, `hclvalidate`, `graph-dependencies`, `validate-inputs`,
`terragrunt-` prefixed flags, the `skip` attribute, `retryable_errors`, and a bare
`find_in_parent_folders()`. Terragrunt v1.0.0 shipped 2026-03-30 and renamed them, so
essentially everything written before that date -- documentation, blog posts, other tooling,
model training data -- uses forms that no longer exist. Whether stating the ban actually
changes what a model emits has never been measured.

THREE ARMS, because two would not separate the policy from the context:

  C  CONTROL. Empty file. run.sh appends no system prompt at all, so the model answers as
     itself. This is the null hypothesis: the model may already avoid pre-1.0 forms, in
     which case the policy is carrying nothing.
  S  SKILL. The whole of SKILL.md. What ships.
  P  POLICY-ABLATED. SKILL.md with hard-policy item 1 -- and only item 1 -- removed. Items
     2 (fact-based generation) and 3 (knowledge freshness) stay, as does every other
     section. S minus P isolates the BAN. C minus P isolates everything else the skill
     knows about Terragrunt.

Without P, a gap between C and S would be unreadable: it could be the ban, or it could be
that any 2,000 words of correct 1.x Terragrunt context is enough on its own.

WHAT THESE ARMS CANNOT MEASURE, said here rather than discovered later.

  THE REFERENCES ARE NOT INLINED. terragrunt-skill is a ROUTER -- SKILL.md tells the agent
  which of ten reference files to grep, and the references total roughly 31,000 words. The
  harness disallows Read and Grep so no arm can reach them, and inlining all ten would both
  cost a fortune per run and test an artifact that does not ship. So this eval bounds the
  effect of SKILL.md, which is where the hard policy lives. It says nothing about whether
  the references are any good. A separate suite would be needed for that.

  IT IS ALSO NOT A CORRECTNESS TEST. Grading is by banned-form detection. An answer can
  score clean and still be wrong in ways this suite cannot see.

Lesson 5 from evals/ablation/README.md applies here: arms/ is gitignored, so REBUILD ALL
THREE whenever SKILL.md moves. An arm built from last week's source compared against one
built today measures the commit, not the ablation.
"""

import argparse
import pathlib
import shutil
import sys

SKILL = pathlib.Path(__file__).resolve().parent.parent
OUT = pathlib.Path(__file__).parent / "arms"
OUT_DISK = pathlib.Path(__file__).parent / "arms-disk"

# What an ON-DISK arm carries. SKILL.md alone is not the skill: it is a ROUTER, and every row
# of its Mode table points at one of these. Without them the agent follows the router into a
# file that is not there, which measures the harness rather than the skill.
DISK_TREE = ("references", "templates", "scripts")

# Exact first and last lines of hard-policy item 1. Matched as text, not by line number, so
# the build fails loudly if the section is edited rather than silently cutting the wrong span.
ITEM1_START = "1. **Post-1.0 CLI only.**"
ITEM2_START = "2. **Fact-based generation.**"

# Every form the policy bans. Arm P must contain NONE of them; arm S must contain all.
BANNED = (
    "run-all", "plan-all", "hclfmt", "hclvalidate", "graph-dependencies",
    "validate-inputs", "retryable_errors",
)



def build_on_disk(ablated: str, md: str) -> None:
    """Write a DIRECTORY per arm instead of one .md, for the routing suite.

    WHY THIS EXISTS. The inlined arms above put SKILL.md in a system prompt and disallow Read,
    Grep and Glob so nothing can reach what was stripped. That bounds the effect of SKILL.md
    cleanly, and it makes two things unmeasurable: the ten reference files (~31,000 words) are
    unreachable, so nothing says whether they are any good; and routing cannot be asked at all,
    because the skill is always on and there is no file for the agent to choose to open.

    Materialising the arm on disk fixes both. The leak is prevented by WHAT IS ON DISK, not by
    removing the tools -- disallowing Read was a blunt instrument that also deleted the thing
    worth measuring.

    ARM P IS CONFOUNDED HERE, and it is worth saying plainly rather than discovering later.
    P is "SKILL.md minus the ban". Once references/ is readable, hcl-blocks.md still says
    retryable_errors was removed in 1.0 and cli-reference.md still gives the 1.x command tree,
    so the ban leaks straight back in through the references. The ablation does not ablate.
    P is still written, because "does removing it from SKILL.md matter when the references are
    reachable" is a real question -- but it is a DIFFERENT question, and the C-vs-S-vs-P
    comparison that produces the published figure stays with the inlined arms.
    """
    if OUT_DISK.exists():
        shutil.rmtree(OUT_DISK)

    # C is the control: NO skill directory at all. Not an empty one -- an empty skill/ is a
    # visible thing for the agent to find and reason about, which is not the same as absence.
    (OUT_DISK / "C").mkdir(parents=True)

    for arm, text in (("S", md), ("P", ablated)):
        root = OUT_DISK / arm / "skill"
        root.mkdir(parents=True)
        (root / "SKILL.md").write_text(text)
        for name in DISK_TREE:
            src = SKILL / name
            if src.is_dir():
                shutil.copytree(src, root / name, ignore=shutil.ignore_patterns(
                    "__pycache__", "*.pyc", ".pytest_cache", ".venv", ".DS_Store"))

    for arm in ("C", "S", "P"):
        files = sorted(p for p in (OUT_DISK / arm).rglob("*") if p.is_file())
        size = sum(p.stat().st_size for p in files)
        note = "  (control: no skill/ directory)" if arm == "C" else ""
        print(f"{arm}: {len(files):>4} files  {size / 1024:>7.0f} KB{note}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    ap.add_argument("--on-disk", action="store_true",
                    help="also write arms-disk/<arm>/ for the routing suite")
    args = ap.parse_args()

    md = (SKILL / "SKILL.md").read_text()

    for marker in (ITEM1_START, ITEM2_START):
        if marker not in md:
            print(f"FAIL: marker missing from SKILL.md: {marker!r}", file=sys.stderr)
            print("      hard-policy item 1 has been edited; fix the markers here.", file=sys.stderr)
            return 1

    i, j = md.index(ITEM1_START), md.index(ITEM2_START)
    ablated = md[:i] + md[j:]
    # Renumber so arm P does not read as a list that starts at 2 -- a visible oddity in the
    # prompt is a difference between arms that has nothing to do with the ablation.
    ablated = ablated.replace(ITEM2_START, "1. **Fact-based generation.**", 1)
    ablated = ablated.replace("3. **Knowledge freshness.", "2. **Knowledge freshness.", 1)

    header = "You have the following skill available. Follow it.\n\n# SKILL: terragrunt-skill\n\n"

    OUT.mkdir(exist_ok=True)
    (OUT / "C.md").write_text("")
    (OUT / "S.md").write_text(header + md)
    (OUT / "P.md").write_text(header + ablated)

    s_len, p_len = len((OUT / "S.md").read_text()), len((OUT / "P.md").read_text())
    cut = s_len - p_len
    print(f"C: {0:>6} chars   (control: no system prompt appended)")
    print(f"S: {s_len:>6} chars")
    print(f"P: {p_len:>6} chars   removes {cut} ({cut / s_len:.1%} of the payload)")

    # Lesson 5: assert a SIZE DECREASE, not just a missing marker. An arm that silently
    # failed to cut anything would otherwise pass every other check here.
    if cut <= 0:
        print(f"FAIL: arm P is not smaller than arm S (delta {cut})", file=sys.stderr)
        return 1

    # Lesson 2: leak-check the ASSEMBLED text, which is the only version the model sees.
    p_text = (OUT / "P.md").read_text()
    leaked = [b for b in BANNED if b in p_text]
    if leaked:
        print(f"FAIL: arm P still names banned forms it was meant to lose: {leaked}", file=sys.stderr)
        return 1
    missing = [b for b in BANNED if b not in (OUT / "S.md").read_text()]
    if missing:
        print(f"FAIL: arm S is missing forms the policy should list: {missing}", file=sys.stderr)
        return 1

    print(f"checked: arm P names none of the {len(BANNED)} banned forms; arm S names all of them")

    if args.on_disk:
        print()
        print("on-disk arms (routing suite):")
        build_on_disk(header + ablated, header + md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
