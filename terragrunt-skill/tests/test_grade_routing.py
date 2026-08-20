"""Tests for the routing grader.

The leak check is the load-bearing part and it earned that on the FIRST real run of this
harness: with `--allowed-tools "Read" "Grep" "Glob"` and nothing else, the agent called Bash
five times and read ~/.claude/skills/terragrunt-skill/references/cli-reference.md -- the
author's real installed skill, outside the sandbox. The design for this suite had argued an
allowlist was SAFER than a denylist because "a denylist is only as good as the list". That was
wrong: --allowed-tools does not restrict what may run, --disallowed-tools does.

A leaked run is not a bad score, it is NOT A MEASUREMENT -- the arm it was meant to test is not
the one it read. So the two failure modes here are asymmetric:

  A MISSED LEAK silently publishes a number produced by reading the real skill off the
  author's disk. Nothing downstream can detect it.

  A FALSE LEAK discards a good run. Wasteful, visible, and it happened immediately: macOS
  mktemp returns /var/folders/... while the agent sees /private/var/folders/..., so the first
  version flagged every in-sandbox read.
"""

import importlib.util
import json
import pathlib

import pytest

EVALS = pathlib.Path(__file__).resolve().parent.parent / "evals"
spec = importlib.util.spec_from_file_location("gr", EVALS / "grade_routing.py")
gr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gr)

BOX = "/private/var/folders/xx/T/tmp.SANDBOX"


# ------------------------------------------------------------------ the leak check

@pytest.mark.parametrize("path", [
    "/Users/kevinburns/.claude/skills/terragrunt-skill/references/cli-reference.md",
    "~/.claude/skills/terragrunt-skill/SKILL.md",
    "/etc/passwd",
    "../../../Users/kevinburns/Developer/claude-skills/terragrunt-skill/SKILL.md",
])
def test_a_read_outside_the_sandbox_is_a_leak(path):
    assert gr.escapes(path, BOX)


@pytest.mark.parametrize("path", [
    f"{BOX}/skill/SKILL.md",
    f"{BOX}/skill/references/cli-reference.md",
    "skill/SKILL.md",
    "./skill/references/hcl-blocks.md",
    "skill/**",
])
def test_a_read_inside_the_sandbox_is_not_a_leak(path):
    assert not gr.escapes(path, BOX)


def test_the_real_leak_that_happened_is_caught():
    """Verbatim from the first run: five Bash calls, three of them reading the author's
    installed skill. Kept as a fixture so the check can never regress past the exact case
    that justified it."""
    calls = [
        ("Bash", {"command": 'test -d ./skill && echo "exists" || echo "missing"'}),
        ("Read", {"file_path": "./skill/SKILL.md"}),
        ("Bash", {"command": "grep -n '^## COMMAND:' ~/.claude/skills/terragrunt-skill/"
                             "references/cli-reference.md"}),
    ]
    leaks = [(n, v) for n, v in gr.paths_touched(calls) if gr.escapes(v, BOX)]
    assert leaks, "the leak that motivated this whole check is not detected"
    assert any("~/.claude" in v for _, v in leaks)


def test_a_bash_command_is_examined_for_paths_not_just_file_path_args():
    """The leak arrived inside a Bash `command` string, not a Read `file_path`. Checking only
    the obvious field is how it got out the first time."""
    touched = gr.paths_touched([("Bash", {"command": "sed -n '1,20p' ~/.claude/skills/x/SKILL.md"})])
    assert touched and any("~/.claude" in v for _, v in touched)


# ------------------------------------------------------------------ routing

def test_opening_a_reference_the_router_names_counts_as_routed(tmp_path):
    row = _row(tmp_path, case="1", opened="skill/references/cli-reference.md")
    assert row["opened"] == ["cli-reference.md"]
    assert row["routed"] is True


def test_opening_the_wrong_reference_is_a_miss(tmp_path):
    row = _row(tmp_path, case="4", opened="skill/references/error-patterns.md")
    assert row["routed"] is False


def test_a_negative_case_is_routed_correctly_by_opening_NOTHING(tmp_path):
    """Cases 8 and 9 ask for plain Terraform and for Kubernetes. Reaching for a Terragrunt
    reference there is over-reach, so an empty `expect` means opening nothing is the pass."""
    assert _row(tmp_path, case="9", opened=None)["routed"] is True
    assert _row(tmp_path, case="9", opened="skill/references/cli-reference.md")["routed"] is False


def test_a_case_with_no_settled_expectation_is_recorded_not_asserted(tmp_path):
    """Cases 11 and 12 carry `expect: null`. Asserting a ground truth nobody has settled would
    manufacture a pass or a fail out of a judgement that was never made."""
    assert _row(tmp_path, case="11", opened="skill/references/hcl-blocks.md")["routed"] is None


def test_an_arm_that_never_opened_the_skill_is_flagged(tmp_path):
    """A run where discovery failed answers from memory and scores as a skill run. One did
    exactly that before the preamble was fixed -- it globbed, missed, and emitted run-all."""
    assert _row(tmp_path, case="1", opened=None, read_skill=False)["read_skill"] is False


# ------------------------------------------------------------------ the router table

def test_the_router_table_is_parsed_from_skill_md_not_copied():
    """Parsed so a router edit propagates. A copy drifts, which is the failure this whole
    skill spent a week removing from its own references."""
    table = gr.router_table()
    assert len(table) >= 8
    assert table.get("DIAGNOSE") == "error-patterns.md"
    assert table.get("REVIEW") == "best-practices.md"
    assert table.get("CICD") == "cicd.md"


def _row(tmp_path, case, opened, read_skill=True):
    calls = []
    if read_skill:
        calls.append({"type": "tool_use", "name": "Read", "input": {"file_path": f"{BOX}/skill/SKILL.md"}})
    if opened:
        calls.append({"type": "tool_use", "name": "Read", "input": {"file_path": f"{BOX}/{opened}"}})
    p = tmp_path / f"{case}-S-1.jsonl"
    p.write_text("\n".join([
        json.dumps({"type": "assistant", "message": {"content": calls}}),
        json.dumps({"type": "result", "result": "answer", "total_cost_usd": 0.1}),
        json.dumps({"_meta": True, "arm": "S", "sandbox": BOX}),
    ]))
    return gr.grade_one(p, json.loads((EVALS / "routing.json").read_text()))
