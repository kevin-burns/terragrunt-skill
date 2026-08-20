#!/usr/bin/env python3
"""Grade the ROUTING suite: did the agent stay in its sandbox, and did it open the right file?

ci-skip: needs-run-bank

WHAT THIS ANSWERS THAT THE OTHER TWO GRADERS CANNOT. grade.py measures one property of the
text a model emitted, with the references unreachable by construction. So it says nothing
about whether the ten reference files are any good, and it cannot ask about routing at all --
the skill is always on, and there is no file for the agent to choose to open.

This grades a stream of TOOL CALLS instead. Three questions, in order of how much they matter:

  1. DID ANY READ LEAVE THE SANDBOX. This is not paranoia. On the FIRST real run of this
     harness, with --allowed-tools "Read" "Grep" "Glob" and nothing else, the agent called
     Bash five times and read ~/.claude/skills/terragrunt-skill/references/cli-reference.md --
     the author's real installed skill. --allowed-tools does not restrict what may run;
     --disallowed-tools does. A leaked run is not a bad score, it is NOT A MEASUREMENT: the
     arm it was supposed to be testing was not the one it read. Discarded and named.

  2. DID IT READ THE SKILL AT ALL. An arm whose SKILL.md was never opened is an expensive
     control. Without this check a run where discovery failed scores as a skill run, and one
     did exactly that before the preamble was fixed: it globbed, missed, gave up, answered
     from memory, and emitted run-all.

  3. WHICH REFERENCE DID IT OPEN. The router in SKILL.md names one per mode. Whether the
     agent followed it is the routing question, and it is the same question jfr992's
     evaluations.json asks by hand.

WHAT IT CANNOT TELL YOU, said here rather than discovered later. It CONFOUNDS ROUTING WITH
CONTENT: a wrong answer does not say whether the router sent it to the wrong file or the right
file failed it. That is why the inlined suite stays -- this is a third suite beside it.
"""

import argparse
import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).parent
SKILL = HERE.parent
ROUTING = HERE / "routing.json"


def router_table() -> dict[str, str]:
    """MODE -> reference, parsed out of SKILL.md's own Mode table.

    Parsed rather than copied so a router edit propagates. What is deliberately NOT derived
    is which mode a case is asking for -- that is a judgement, and it lives in routing.json
    with its reasoning written beside it."""
    text = (SKILL / "SKILL.md").read_text()
    out = {}
    for row in re.findall(r"^\|([^|]+)\|([^|]+)\|([^|]+)\|$", text, re.M):
        mode = row[1].strip().strip("*_ ")
        refs = re.findall(r"references/([a-z0-9-]+\.md)", row[2])
        if mode and refs:
            out[mode] = refs[0]
    return out


def events(path: pathlib.Path) -> tuple[list[dict], dict]:
    """(stream events, the _meta line run_routing.sh appended)."""
    evts, meta = [], {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        (meta.update(d) if d.get("_meta") else evts.append(d))
    return evts, meta


def tool_calls(evts: list[dict]) -> list[tuple[str, dict]]:
    out = []
    for d in evts:
        for blk in (d.get("message") or {}).get("content") or []:
            if isinstance(blk, dict) and blk.get("type") == "tool_use":
                out.append((blk.get("name", "?"), blk.get("input") or {}))
    return out


# Every field a read-shaped tool puts a path in. Checked by NAME rather than by tool, so a
# tool nobody anticipated still has its paths examined.
PATH_FIELDS = ("file_path", "path", "pattern", "notebook_path", "command")


# A path can be the whole argument (Read file_path) or buried in a command string
# (`grep -n '^## COMMAND:' ~/.claude/skills/.../cli-reference.md`). The first version checked
# only whole values, so it saw a string starting with "grep" and called it relative -- missing
# the actual leak it was written for. Tokens, not whole values.
PATH_TOKEN = re.compile(r"(?:~|\.{1,2}/|/)[^\s'\"`;|&)]*")


def paths_touched(calls: list[tuple[str, dict]]) -> list[tuple[str, str]]:
    out = []
    for name, args in calls:
        for field in PATH_FIELDS:
            value = args.get(field)
            if not isinstance(value, str):
                continue
            if field != "command":
                # The whole argument IS the path. Tokenising these was wrong in the other
                # direction: a Glob pattern of `**/SKILL.md` yields the token `/SKILL.md`,
                # which reads as absolute and flagged three good runs as leaks.
                out.append((name, value))
                continue
            # Only a shell command hides paths inside a larger string, and that is exactly
            # where the real leak came from: `grep -n '...' ~/.claude/skills/.../x.md`.
            for token in PATH_TOKEN.findall(value):
                if len(token) > 1:
                    out.append((name, token))
    return out


def escapes(value: str, sandbox: str) -> bool:
    """A path that reaches outside the sandbox. Relative paths are in-sandbox by definition --
    cwd IS the sandbox -- unless they climb out with ..; absolute ones must be under it."""
    if value.startswith("~"):
        return True
    if value.startswith("/"):
        return not value.startswith(sandbox.rstrip("/") + "/") and value != sandbox
    return ".." in pathlib.PurePosixPath(value).parts


def refs_opened(calls: list[tuple[str, dict]]) -> list[str]:
    seen = []
    for _, args in calls:
        for field in PATH_FIELDS:
            value = args.get(field)
            if isinstance(value, str):
                for m in re.findall(r"references/([a-z0-9-]+\.md)", value):
                    if m not in seen:
                        seen.append(m)
    return seen


def read_skill_md(calls: list[tuple[str, dict]]) -> bool:
    return any(
        isinstance(args.get(f), str) and args[f].endswith("skill/SKILL.md")
        for name, args in calls if name in ("Read", "Grep")
        for f in ("file_path", "path")
    )


def grade_one(path: pathlib.Path, expectations: dict) -> dict:
    m = re.fullmatch(r"(\d+)-([CSP])-(\d+)", path.stem)
    if not m:
        return {}
    case, arm, rep = m.groups()
    evts, meta = events(path)
    calls = tool_calls(evts)
    # Both forms: the resolved path is what the agent sees, the raw one is what mktemp
    # returned, and older runs recorded only the raw one.
    boxes = [b for b in (meta.get("sandbox"), meta.get("sandbox_raw")) if b]
    boxes += [os.path.realpath(b) for b in boxes]
    leaks = [(n, v) for n, v in paths_touched(calls)
             if boxes and all(escapes(v, b) for b in boxes)]
    opened = refs_opened(calls)
    expect = (expectations.get(case) or {}).get("expect")

    if expect is None:
        routed = None                       # record only; no ground truth asserted
    elif not expect:
        routed = not opened                 # negative case: opening nothing is correct
    else:
        routed = bool(set(opened) & set(expect))

    result = next((d.get("result") or "" for d in evts if d.get("type") == "result"), "")
    cost = next((d.get("total_cost_usd") or 0 for d in evts if d.get("type") == "result"), 0)
    return {
        "case": case, "arm": arm, "rep": rep,
        "leaks": leaks, "opened": opened, "expect": expect, "routed": routed,
        # None for the control: it has no skill/ directory, so the question does not apply.
        # A failed Read still appears as a tool_use, and reporting that as "read the skill"
        # made arm C look like it had loaded something that was never there.
        "read_skill": None if arm == "C" else read_skill_md(calls), "calls": len(calls),
        "cost": float(cost), "chars": len(result),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    ap.add_argument("--runs-dir", default="runs-routing")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero on any leaked run or any missed route")
    args = ap.parse_args()

    runs = sorted((HERE / args.runs_dir).glob("*.jsonl"))
    if not runs:
        print(f"No runs in {HERE / args.runs_dir}. Build the arms and run the matrix:",
              file=sys.stderr)
        print("  uv run evals/build_arms.py --on-disk && ./evals/matrix_routing.sh",
              file=sys.stderr)
        return 1

    expectations = json.loads(ROUTING.read_text())
    rows = [r for r in (grade_one(p, expectations) for p in runs) if r]

    table = router_table()
    print(f"BANK: {args.runs_dir}/   RUNS: {len(rows)}   "
          f"router rows parsed from SKILL.md: {len(table)}")
    print()

    leaked = [r for r in rows if r["leaks"]]
    if leaked:
        print("LEAKED -- these runs read outside their sandbox and are NOT MEASUREMENTS.")
        print("  The arm they were meant to test is not the one they read. Discard and re-run.")
        for r in leaked:
            for name, value in r["leaks"][:3]:
                print(f"  {r['case']}-{r['arm']}-{r['rep']}  {name}  {value[:88]}")
        print()

    clean = [r for r in rows if not r["leaks"]]
    print(f"  {'cell':<10}{'skill?':>8}{'calls':>7}{'routed':>9}  opened")
    for r in clean:
        # The control is never expected to route: it has no router. Showing "NO" beside it
        # reads as a failure of something that was never asked.
        routed = "n/a" if r["arm"] == "C" else {True: "yes", False: "NO", None: "—"}[r["routed"]]
        skill = {True: "yes", False: "NO", None: "n/a"}[r["read_skill"]]
        cell = f"{r['case']}-{r['arm']}-{r['rep']}"
        print(f"  {cell:<10}{skill:>8}{r['calls']:>7}{routed:>9}  {', '.join(r['opened']) or '—'}")

    asserted = [r for r in clean if r["routed"] is not None and r["arm"] != "C"]
    hit = sum(1 for r in asserted if r["routed"])
    inert = [r for r in clean if r["arm"] != "C" and not r["read_skill"]]
    print()
    if asserted:
        print(f"ROUTING: {hit}/{len(asserted)} skill-arm runs opened a reference the router names.")
    if inert:
        print(f"INERT:   {len(inert)} skill-arm run(s) never opened SKILL.md -- an expensive "
              "control, not a skill run.")
    print(f"COST:    ${sum(r['cost'] for r in rows):.2f} across {len(rows)} runs.")

    if args.strict and (leaked or inert or (asserted and hit < len(asserted))):
        print("\nFAIL: --strict", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
