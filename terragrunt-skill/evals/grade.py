#!/usr/bin/env python3
"""Grade the policy-compliance matrix: how often does each arm emit a pre-1.0 Terragrunt form?

Terragrunt v1.0.0 (2026-03-30) renamed much of the CLI. terragrunt-skill's first hard-policy
rule bans the old forms outright. This scores whether stating that ban changes what the model
emits, against a control that was never given the skill at all.

THE ONE THING THAT MAKES THIS HARDER THAN A GREP, and the reason for the adjudication step:

    "Use `run --all plan`. (The old `run-all` was removed in 1.0.)"

is CORRECT behaviour -- the model named the obsolete form in order to warn about it. A naive
grep scores that identically to

    "Run `terragrunt run-all plan`."

which is the failure this suite exists to catch. Counting them together would report the
skill's own warning as a violation and could invert the result. So every hit is classified,
every hit is written out with its surrounding text, and the headline numbers are refused
until a human has read them.

ci-skip: needs-run-bank

CI cannot run this end to end and should not pretend to. It grades runs/, a bank of model
responses that is gitignored on purpose: an arm is built from SKILL.md, so a banked run has to
be regenerated whenever SKILL.md moves, and committing one guarantees today's arm gets compared
against last week's answer. There is nothing in a fresh checkout to grade.

That is NOT a coverage hole. The part of this file that could be wrong is the detection and
classification, and 40 tests in tests/test_eval_grade.py cover it against committed fixtures.
What CI cannot do is re-run the experiment, which costs money and is a decision.

Lesson 4 of evals/ablation/README.md is the precedent: an earlier metric there scored correct
placeholder behaviour as fabrication and reported p = 0.0017 for an effect that was partly an
artefact. Only the class that survived reading every hit individually was published.

Usage:
    uv run evals/grade.py                      # classify, write hits.jsonl, print provisional
    uv run evals/grade.py --adjudicate         # open questions only, as a worksheet
    uv run evals/grade.py --final              # refuse to print unless every hit is adjudicated
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from collections import defaultdict

HERE = pathlib.Path(__file__).parent
RUNS = HERE / "runs"
HITS = HERE / "hits.jsonl"
ADJ = HERE / "adjudications.json"

# Every form hard-policy item 1 bans, with the 1.x replacement for the report.
# `skip` and `find_in_parent_folders` need shape, not just the word: `skip` is ordinary
# English and `find_in_parent_folders("root.hcl")` is the CORRECT 1.x call -- only the
# argument-less form is banned.
FORMS: tuple[tuple[str, str, str], ...] = (
    ("run-all",            r"\brun-all\b",                              "run --all"),
    ("plan-all",           r"\bplan-all\b",                             "run --all -- plan"),
    ("apply-all",          r"\bapply-all\b",                            "run --all -- apply"),
    ("destroy-all",        r"\bdestroy-all\b",                          "run --all -- destroy"),
    ("output-all",         r"\boutput-all\b",                           "run --all -- output"),
    ("validate-all",       r"\bvalidate-all\b",                         "run --all -- validate"),
    ("hclfmt",             r"\bhclfmt\b",                               "hcl fmt"),
    ("hclvalidate",        r"\bhclvalidate\b",                          "hcl validate"),
    ("graph-dependencies", r"\bgraph-dependencies\b",                   "dag graph"),
    ("validate-inputs",    r"\bvalidate-inputs\b",                      "hcl validate --inputs"),
    ("--terragrunt-flag",  r"--terragrunt-[a-z][a-z0-9-]*",             "the same flag without the prefix"),
    ("skip-attribute",     r"\bskip\s*=\s*(?:true|false)",              "an exclude block"),
    ("retryable_errors",   r"\bretryable_errors\b",                     "an errors block"),
    ("bare-fipf",          r"find_in_parent_folders\(\s*\)",            'find_in_parent_folders("root.hcl")'),
)

# Whether a hit is a VIOLATION or merely ADVISORY turns on whether the model named the form
# in order to warn about it. Two tiers, because one window does not fit both kinds of signal.
#
# STRONG signals are rarely incidental -- "deprecated", "removed in", "renamed" next to a
# pre-1.0 form nearly always means the model is flagging it. They get the full window.
#
# WEAK signals are ordinary prose that happens to appear near anything. The first version of
# this used one wide window for both and misread 8 of 10 hits in a run that was plainly
# recommending the forms: "instead of" had turned up elsewhere in the answer, about something
# else entirely. Weak signals must now sit right beside the match to count.
STRONG = re.compile(
    r"deprecat|obsolete|no longer|removed in|renamed|superseded|formerly|used to be|"
    r"pre-1\.0|before 1\.0|0\.x|legacy",
    re.I,
)
WEAK = re.compile(
    r"instead of|rather than|replaced|don't use|do not use|not valid|invalid|"
    r"old(er)? (form|syntax|name|command|way)|old\s+`",
    re.I,
)

CONTEXT = 260   # chars either side, for the human reading the hit and for STRONG signals
NEAR = 60       # chars either side that a WEAK signal must fall within to count
ENCLOSING = 400 # chars to look BACK for a block that makes an otherwise-banned name legal

# `retryable_errors` is a BANNED top-level attribute and a VALID attribute inside the 1.x
# `errors { retry "name" { ... } }` block. Same string, opposite verdicts. The first run of
# this eval scored five correct 1.x answers as violations for exactly this reason and made the
# skill look ineffective on case 6. Where a form is legal inside some enclosing block, name it
# here and the grader looks backwards for that block before condemning the hit.
LEGAL_INSIDE: dict[str, re.Pattern] = {
    "retryable_errors": re.compile(r"errors\s*\{|retry\s+\"", re.I),
}
NEAR = 60       # chars either side that a WEAK signal must fall within to count

  # chars either side, enough to see the sentence and any surrounding fence


def run_files(runs_dir: pathlib.Path = RUNS) -> list[pathlib.Path]:
    return sorted(runs_dir.glob("*.json"))


def parse_name(p: pathlib.Path) -> tuple[str, str, str] | None:
    m = re.fullmatch(r"(\d+)-([CSP])-(\d+)", p.stem)
    return (m.group(1), m.group(2), m.group(3)) if m else None


def arm_provenance(files: list[pathlib.Path]) -> tuple[dict[str, str], list[str], list[str]]:
    """Which arm each banked run was ACTUALLY given, against the arms on disk now.

    Until 2026-08-20 the only thing linking a run to its arm was a comment in matrix.sh
    saying to move runs/ aside when SKILL.md moved. That instruction went stale the same day
    it was written -- the arms were built at 22:29 on 08-19, SKILL.md moved at 09:38 the next
    morning, and nothing anywhere noticed. Comparing today's arm against last week's answer is
    the one way this harness can produce a confidently wrong number.

    Returns (current arm hashes, stale run names, unstamped run names). UNSTAMPED means the
    run predates the stamp: it cannot be verified either way, which is not the same as being
    wrong and is not reported as if it were.
    """
    current = {}
    for arm in ("C", "S", "P"):
        path = HERE / "arms" / f"{arm}.md"
        if path.exists():
            current[arm] = hashlib.sha256(path.read_bytes()).hexdigest()

    stale, unstamped = [], []
    for p in files:
        parsed = parse_name(p)
        if not parsed:
            continue
        _, arm, _ = parsed
        try:
            env = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue          # damaged; result_text already reports it
        stamped = env.get("arm_sha256")
        if not stamped:
            unstamped.append(p.stem)
        elif arm in current and stamped != current[arm]:
            stale.append(p.stem)
    return current, sorted(stale), sorted(unstamped)


def filter_cases(files: list[pathlib.Path], spec: str) -> list[pathlib.Path]:
    """Keep only the runs for the named cases. Exists because pooling the positive suite with
    the negative one produces a real number that answers a question nobody asked, and it looks
    enough like the headline to be quoted in its place."""
    wanted = {c.strip() for c in spec.split(",") if c.strip()}
    return [p for p in files if (parse_name(p) or ("",))[0] in wanted]


def result_text(p: pathlib.Path) -> tuple[str, float]:
    try:
        raw = p.read_text()
    except OSError:
        return "", 0.0
    try:
        env = json.loads(raw)
    except json.JSONDecodeError:
        # Trailing bytes after a complete envelope mean two writers shared this path. Take the
        # first complete value so the run is not lost, but SAY SO -- silently treating a
        # damaged file as an empty result quietly drops it from the denominator, and on
        # 2026-08-19 that removed 9 of 63 cells unevenly across arms before anyone noticed.
        try:
            env, end = json.JSONDecoder().raw_decode(raw, 0)
        except json.JSONDecodeError:
            print(f"  DAMAGED {p.name}: no complete JSON envelope; excluded")
            return "", 0.0
        print(f"  DAMAGED {p.name}: {len(raw) - end} trailing bytes after a complete envelope "
              f"(concurrent writers). Using the first envelope -- re-run this cell.")
    text = env.get("result") or ""
    if not isinstance(text, str):
        text = json.dumps(text)
    return text, float(env.get("total_cost_usd") or 0.0)


def hit_id(case: str, arm: str, rep: str, form: str, snippet: str, bank: str = "runs") -> str:
    """Stable across reruns of the grader, so adjudications survive. Keyed on the snippet
    rather than the byte offset, because an offset shifts when anything upstream changes.

    `bank` is the runs directory. The default contributes NOTHING to the hash, so the 245
    verdicts already recorded against the Claude bank stay valid. Any other bank is mixed in,
    because two models emitting the same snippet in the same cell would otherwise share an id
    and inherit each other's verdict."""
    prefix = "" if bank == "runs" else f"{bank}|"
    h = hashlib.sha256(f"{prefix}{case}|{arm}|{rep}|{form}|{snippet.strip()}".encode()).hexdigest()
    return h[:12]


def find_hits(text: str, case: str, arm: str, rep: str, bank: str = "runs") -> list[dict]:
    out = []
    for form, pattern, replacement in FORMS:
        for m in re.finditer(pattern, text):
            lo, hi = max(0, m.start() - CONTEXT), min(len(text), m.end() + CONTEXT)
            context = text[lo:hi]
            near = text[max(0, m.start() - NEAR):min(len(text), m.end() + NEAR)]
            back = text[max(0, m.start() - ENCLOSING):m.start()]
            legal = LEGAL_INSIDE.get(form)
            if legal and legal.search(back):
                auto = "valid-1x"
            elif STRONG.search(context) or WEAK.search(near):
                auto = "advisory"
            else:
                auto = "violation"
            out.append({
                "id": hit_id(case, arm, rep, form, m.group(0) + context[:80], bank),
                "case": case, "arm": arm, "rep": rep,
                "form": form, "matched": m.group(0), "should_be": replacement,
                "auto": auto, "context": context,
            })
    return out


def load_adjudications(adj_path: pathlib.Path = ADJ) -> dict[str, str]:
    ADJ = adj_path  # noqa: N806 -- keeps the messages below naming the real file
    if not ADJ.exists():
        return {}
    try:
        data = json.loads(ADJ.read_text())
    except json.JSONDecodeError as e:
        print(f"FAIL: {ADJ.name} is not valid JSON: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    bad = {k: v for k, v in data.items() if v not in ("violation", "advisory", "valid-1x")}
    if bad:
        print(f"FAIL: verdicts must be 'violation', 'advisory' or 'valid-1x'; got {bad}",
              file=sys.stderr)
        raise SystemExit(1)
    return data


def report(hits: list[dict], files: list[pathlib.Path], adj: dict[str, str], final: bool,
           bank: str = "runs", hits_name: str = "hits.jsonl",
           adj_name: str = "adjudications.json") -> int:
    verdict = {h["id"]: adj.get(h["id"], h["auto"]) for h in hits}
    unadjudicated = [h for h in hits if h["id"] not in adj]

    runs = defaultdict(list)          # arm -> [n_violations per run]
    cell = defaultdict(dict)          # (case, arm) -> rep -> n_violations
    cost = 0.0
    for p in files:
        parsed = parse_name(p)
        if not parsed:
            continue
        case, arm, rep = parsed
        text, c = result_text(p)
        cost += c
        if not text:
            print(f"  WARN {p.name}: empty result -- run failed or was truncated; excluded")
            continue
        n = sum(1 for h in hits
                if (h["case"], h["arm"], h["rep"]) == (case, arm, rep)
                and verdict[h["id"]] == "violation")
        runs[arm].append(n)
        cell[(case, arm)][rep] = n

    print()
    cases_in = sorted({parse_name(p)[0] for p in files if parse_name(p)}, key=int)
    print(f"BANK: {bank}/   CASES: {','.join(cases_in)}   RUNS: {len(files)}")
    _, stale, unstamped = arm_provenance(files)
    if stale:
        print()
        print(f"  STALE ARM: {len(stale)} run(s) were produced by a DIFFERENT arm than the one")
        print("  on disk now. SKILL.md has moved since they were banked, so these compare")
        print("  today's skill against last week's answer. Re-run them, or move the bank aside:")
        print("    " + ", ".join(stale[:8]) + (" ..." if len(stale) > 8 else ""))
    if unstamped:
        print(f"      {len(unstamped)} run(s) carry no arm hash -- banked before stamping "
              "began on 2026-08-20.")
        print("      Their provenance cannot be verified either way. Re-run to clear.")
    if bank != "runs":
        print("      NOT the Claude bank. These runs are a separate experiment and must not")
        print("      be pooled with, or quoted in place of, the runs/ measurement.")
    elif cases_in != ["1", "2", "3", "4", "5", "6", "7"]:
        print("      This is NOT the headline set. The published figure is cases 1-7 only:")
        print("      grade.py --cases 1,2,3,4,5,6,7")
    print()
    print("PRE-1.0 EMISSION BY ARM")
    print("  C = control (no skill)   S = full SKILL.md   P = SKILL.md minus the ban")
    print()
    print(f"  {'arm':<5}{'runs':>6}{'runs w/ >=1':>13}{'rate':>8}{'total':>8}{'mean/run':>10}")
    for arm in ("C", "S", "P"):
        v = runs.get(arm, [])
        if not v:
            continue
        dirty = sum(1 for n in v if n)
        print(f"  {arm:<5}{len(v):>6}{dirty:>13}{dirty / len(v):>8.0%}{sum(v):>8}{sum(v) / len(v):>10.2f}")

    # Lesson 3: a between-arm gap is unreadable without knowing how much replicates of the
    # SAME arm disagree. This is that floor, and it is printed whether or not it is flattering.
    print()
    print("REPLICATE NOISE FLOOR")
    unstable = [(c, a) for (c, a), reps in cell.items()
                if len({1 if n else 0 for n in reps.values()}) > 1]
    total_cells = len(cell)
    if total_cells:
        print(f"  {len(unstable)}/{total_cells} case x arm cells disagree with themselves across replicates"
              f" ({len(unstable) / total_cells:.0%}).")
        if unstable:
            print("  unstable: " + ", ".join(f"case {c} arm {a}" for c, a in sorted(unstable)))
        print("  A difference between arms smaller than this floor is not readable as an effect.")

    print()
    print("BY CASE (violations summed over replicates)")
    cases = sorted({c for c, _ in cell}, key=int)
    print(f"  {'case':<6}{'C':>5}{'S':>5}{'P':>5}   bait")
    baits = {
        "1": "run-all / plan-all", "2": "hclfmt", "3": "validate-inputs",
        "4": "bare find_in_parent_folders", "5": "skip attribute",
        "6": "retryable_errors", "7": "--terragrunt-* flags",
    }
    for c in cases:
        row = "".join(f"{sum(cell.get((c, a), {}).values()):>5}" for a in ("C", "S", "P"))
        print(f"  {c:<6}{row}   {baits.get(c, '')}")

    print()
    n = lambda k: sum(1 for h in hits if verdict[h["id"]] == k)  # noqa: E731
    print(f"HITS: {len(hits)} total | {n('violation')} violations | {n('advisory')} advisory "
          f"(named to warn) | {n('valid-1x')} valid 1.x usage inside an allowing block.")
    print(f"      {len(unadjudicated)} not yet read by a human. Written to {hits_name}.")
    print(f"COST: ${cost:.2f} across {len(files)} runs.")

    if unadjudicated:
        print()
        print("  THESE NUMBERS ARE PROVISIONAL. The advisory/violation split above is a regex")
        print(f"  guess. Read the hits and record verdicts in {adj_name} as")
        print('  {"<id>": "violation"} or {"<id>": "advisory"} before quoting anything.')
        if final:
            print()
            print(f"FAIL: --final requires every hit adjudicated; {len(unadjudicated)} outstanding.",
                  file=sys.stderr)
            return 1
    if final and stale:
        print()
        print(f"FAIL: --final refuses a stale arm; {len(stale)} run(s) were produced by an arm "
              "that no longer matches SKILL.md.", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    ap.add_argument("--adjudicate", action="store_true",
                    help="print only the hits with no human verdict, as a worksheet")
    ap.add_argument("--final", action="store_true",
                    help="exit non-zero unless every hit has been adjudicated")
    ap.add_argument("--runs-dir", default="runs",
                    help="which bank to grade (default runs/, the Claude measurement). A "
                         "cross-model bank written by run_model.py lives in runs-<model>/ and "
                         "carries its own adjudications file.")
    ap.add_argument("--cases", default=None,
                    help="comma-separated case ids, e.g. 1,2,3,4,5,6,7 for the published "
                         "positive suite. Without it every case in the bank is pooled, which "
                         "produces a real number that answers a question nobody asked.")
    args = ap.parse_args()

    runs_dir = HERE / args.runs_dir
    bank = runs_dir.name
    hits_path = HITS if bank == "runs" else HERE / f"hits-{bank}.jsonl"
    # A separate verdict file per bank. Merging another model's hits into adjudications.json
    # would put unread verdicts behind the --final gate that guards the published figure.
    adj_path = ADJ if bank == "runs" else HERE / f"adjudications-{bank}.json"

    files = run_files(runs_dir)
    if not files:
        print(f"No runs in {runs_dir}. Build the arms and run the matrix first:", file=sys.stderr)
        print("  uv run evals/build_arms.py && ./evals/matrix.sh", file=sys.stderr)
        return 1

    if args.cases:
        kept = filter_cases(files, args.cases)
        if not kept:
            print(f"No runs in {runs_dir} for cases {args.cases}.", file=sys.stderr)
            return 1
        files = kept

    hits: list[dict] = []
    for p in files:
        parsed = parse_name(p)
        if not parsed:
            continue
        text, _ = result_text(p)
        hits.extend(find_hits(text, *parsed, bank=bank))

    hits_path.write_text("".join(json.dumps(h) + "\n" for h in hits))
    adj = load_adjudications(adj_path)

    if args.adjudicate:
        pending = [h for h in hits if h["id"] not in adj]
        if not pending:
            print("Every hit has a human verdict.")
            return 0
        for h in pending:
            print("=" * 78)
            print(f"{h['id']}  case {h['case']} arm {h['arm']} rep {h['rep']}  "
                  f"{h['form']}  matched: {h['matched']!r}")
            print(f"1.x form: {h['should_be']}   regex guess: {h['auto']}")
            print("-" * 78)
            print(h["context"].strip())
            print()
        print(f"{len(pending)} to adjudicate. Record them in {adj_path.name}.")
        return 0

    return report(hits, files, adj, args.final, bank, hits_path.name, adj_path.name)


if __name__ == "__main__":
    raise SystemExit(main())
