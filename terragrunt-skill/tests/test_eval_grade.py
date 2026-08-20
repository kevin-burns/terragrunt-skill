"""Tests for the policy-compliance grader's detection and classification.

The grader decides the number this eval publishes, so its two failure modes both matter:

  A FALSE POSITIVE inflates the violation count and could invent an effect. The dangerous
  ones are ordinary English (`skip`) and the CORRECT 1.x call
  (`find_in_parent_folders("root.hcl")`), which differs from the banned form only by having
  an argument.

  A FALSE NEGATIVE hides a real emission, which is worse for the blog post than for the
  skill -- it would let a claim be published that the runs do not support.

The advisory/violation split is a heuristic and is NOT tested for accuracy here, because it
cannot be: it exists to route hits to a human, not to replace one. What is tested is that it
routes the obvious cases the right way and never silently drops a hit.
"""

import hashlib
import importlib.util
import json
import pathlib

spec = importlib.util.spec_from_file_location(
    "grade", pathlib.Path(__file__).resolve().parent.parent / "evals" / "grade.py"
)
grade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grade)


def forms(text):
    return sorted({h["form"] for h in grade.find_hits(text, "1", "C", "1")})


def verdicts(text):
    return [(h["form"], h["auto"]) for h in grade.find_hits(text, "1", "C", "1")]


# --- the banned forms are detected -------------------------------------------------------

def test_detects_run_all():
    assert "run-all" in forms("Run `terragrunt run-all plan` from the root.")


def test_detects_each_x_all_variant():
    for cmd in ("plan-all", "apply-all", "destroy-all", "output-all", "validate-all"):
        assert cmd in forms(f"Use terragrunt {cmd} here."), cmd


def test_detects_hclfmt_and_hclvalidate():
    assert forms("terragrunt hclfmt && terragrunt hclvalidate") == ["hclfmt", "hclvalidate"]


def test_detects_graph_dependencies_and_validate_inputs():
    assert "graph-dependencies" in forms("terragrunt graph-dependencies | dot -Tpng")
    assert "validate-inputs" in forms("terragrunt validate-inputs --strict")


def test_detects_terragrunt_prefixed_flags():
    hits = grade.find_hits("--terragrunt-working-dir ./live --terragrunt-non-interactive",
                           "1", "C", "1")
    assert [h["matched"] for h in hits] == ["--terragrunt-working-dir", "--terragrunt-non-interactive"]


def test_detects_retryable_errors():
    assert "retryable_errors" in forms('retryable_errors = ["(?s).*Throttling.*"]')


# --- the false positives that would break the metric --------------------------------------

def test_plain_english_skip_is_not_the_attribute():
    """`skip` is an ordinary word. Only `skip = true|false` is the banned attribute."""
    assert forms("You can skip that step, and Terragrunt will skip ahead.") == []


def test_skip_attribute_is_detected_with_either_boolean():
    assert "skip-attribute" in forms("skip = true")
    assert "skip-attribute" in forms("skip  =  false")


def test_correct_find_in_parent_folders_is_not_a_hit():
    """The 1.x call takes an argument. Only the argument-less form is banned, so the
    correct answer must not be scored as a violation."""
    assert forms('include "root" { path = find_in_parent_folders("root.hcl") }') == []


def test_bare_find_in_parent_folders_is_a_hit():
    assert "bare-fipf" in forms('path = find_in_parent_folders()')
    assert "bare-fipf" in forms('path = find_in_parent_folders( )')


def test_run_all_inside_a_longer_word_is_not_matched():
    assert forms("the prerun-allocation step") == []


def test_modern_run_all_form_is_not_a_hit():
    """`run --all` is the correct 1.x form and must never be counted."""
    assert forms("terragrunt run --all -- plan") == []


# --- advisory vs violation routing ---------------------------------------------------------

def test_naming_a_form_to_deprecate_it_routes_to_advisory():
    text = "Use `run --all` instead. The old `run-all` was removed in Terragrunt 1.0."
    assert verdicts(text) == [("run-all", "advisory")]


def test_recommending_a_form_routes_to_violation():
    assert verdicts("Just run `terragrunt run-all plan`.") == [("run-all", "violation")]


def test_advisory_signal_is_case_insensitive():
    assert verdicts("`hclfmt` is DEPRECATED; use `hcl fmt`.") == [("hclfmt", "advisory")]


def test_advisory_classification_never_drops_the_hit():
    """An advisory verdict must still appear in hits.jsonl for a human to read -- the
    classifier routes, it does not filter."""
    hits = grade.find_hits("`run-all` is deprecated.", "1", "C", "1")
    assert len(hits) == 1


# --- hit identity ---------------------------------------------------------------------------

def test_hit_ids_are_stable_across_calls():
    """Adjudications are keyed on the id, so a second grader run must not orphan them."""
    a = grade.find_hits("terragrunt run-all plan", "1", "C", "1")[0]["id"]
    b = grade.find_hits("terragrunt run-all plan", "1", "C", "1")[0]["id"]
    assert a == b


def test_hit_ids_differ_across_arms():
    a = grade.find_hits("terragrunt run-all plan", "1", "C", "1")[0]["id"]
    b = grade.find_hits("terragrunt run-all plan", "1", "S", "1")[0]["id"]
    assert a != b


def test_every_declared_form_has_a_replacement():
    """The report prints the 1.x form beside each hit; a blank would be useless to a reader."""
    for name, _pattern, replacement in grade.FORMS:
        assert replacement and replacement.strip(), name


# --- the two-tier advisory classifier -------------------------------------------------------
# The first version used one wide window for every signal and misread 8 of 10 hits in a run
# that was plainly recommending the forms: "instead of" appeared elsewhere in the answer,
# about something unrelated. These pin the fix.

def test_weak_signal_far_from_the_match_does_not_excuse_it():
    text = ("Run plan instead of apply while you are checking. " + "x" * 120 +
            " Then use `terragrunt run-all plan`.")
    assert verdicts(text) == [("run-all", "violation")]


def test_weak_signal_beside_the_match_does_excuse_it():
    assert verdicts("Use `run --all` instead of `run-all`.") == [("run-all", "advisory")]


def test_strong_signal_counts_at_a_distance():
    """'deprecated' near a pre-1.0 form is almost never incidental, so it keeps the wide
    window that weak signals lost."""
    text = "`hclfmt` " + "y" * 200 + " and that spelling was deprecated in 1.0."
    assert verdicts(text) == [("hclfmt", "advisory")]


def test_a_recommended_flag_with_unrelated_prose_is_a_violation():
    text = ("Pass `--terragrunt-non-interactive` in CI. It is quicker than answering, and "
            "you should avoid interactive prompts on a runner." )
    assert ("--terragrunt-flag", "violation") in verdicts(text)


# --- same string, opposite verdicts -----------------------------------------------------------
# `retryable_errors` is BANNED as a top-level attribute and VALID inside the 1.x
# `errors { retry "name" { ... } }` block. The first run of the eval scored five correct 1.x
# answers as violations for this reason, and made the skill look ineffective on case 6.

def test_retryable_errors_at_top_level_is_a_violation():
    text = '''
    Add this to your terragrunt.hcl:

    retryable_errors = [
      "(?s).*ThrottlingException.*",
    ]
    '''
    assert verdicts(text) == [("retryable_errors", "violation")]


def test_retryable_errors_inside_the_1x_errors_block_is_valid():
    text = '''
    errors {
      retry "transient_aws_errors" {
        retryable_errors = [
          "(?i)ThrottlingException",
        ]
        max_attempts = 5
      }
    }
    '''
    assert verdicts(text) == [("retryable_errors", "valid-1x")]


def test_the_enclosing_block_only_counts_when_it_actually_precedes():
    """An `errors` block appearing AFTER the hit must not retroactively excuse it."""
    text = 'retryable_errors = ["x"]\n' + "z" * 200 + "\nerrors {\n  retry \"later\" {}\n}"
    assert verdicts(text) == [("retryable_errors", "violation")]


def test_valid_1x_is_still_recorded_as_a_hit():
    """A valid-1x verdict routes the hit out of the violation count but must not hide it."""
    hits = grade.find_hits('errors { retry "r" { retryable_errors = ["x"] } }', "6", "S", "1")
    assert len(hits) == 1
    assert hits[0]["auto"] == "valid-1x"


def test_the_old_backticked_form_reads_as_advisory():
    """'not the old `hclvalidate`' was scored a violation because the weak pattern required
    old followed by form/syntax/name/command/way, and the word was followed by a backtick."""
    text = "Validate with `terragrunt hcl validate` (not the old `hclvalidate`) after adding this."
    assert verdicts(text) == [("hclvalidate", "advisory")]


# --------------------------------------------------------------------- suite separation

def test_the_case_filter_keeps_the_two_suites_apart():
    """Cases 1-7 are the positive suite and carry the published figure; 8-12 are negative and
    are a null on every arm. Pooling them produces a real number that answers a question
    nobody asked, and it looks enough like the headline to be quoted in its place."""
    files = [pathlib.Path(f"{c}-C-1.json") for c in (1, 3, 7, 8, 10, 12)]
    kept = [p.name for p in grade.filter_cases(files, "1,2,3,4,5,6,7")]
    assert kept == ["1-C-1.json", "3-C-1.json", "7-C-1.json"]


def test_the_case_filter_tolerates_spaces_and_ignores_unknown_cases():
    files = [pathlib.Path("1-C-1.json"), pathlib.Path("8-S-2.json")]
    assert [p.name for p in grade.filter_cases(files, " 1 , 8 ")] == ["1-C-1.json", "8-S-2.json"]
    assert grade.filter_cases(files, "99") == []


def test_a_file_that_is_not_a_cell_is_dropped_rather_than_crashing():
    """hits.jsonl and adjudications.json live beside the bank; a stray .json must not take
    the grader down mid-run."""
    files = [pathlib.Path("1-C-1.json"), pathlib.Path("adjudications.json")]
    assert [p.name for p in grade.filter_cases(files, "1")] == ["1-C-1.json"]


# --------------------------------------------------------------------- arm provenance

def _bank(tmp_path, monkeypatch, runs: dict, arms: dict):
    """A throwaway evals/ layout: arms/<A>.md plus runs/<case>-<arm>-<rep>.json."""
    (tmp_path / "arms").mkdir()
    for arm, text in arms.items():
        (tmp_path / "arms" / f"{arm}.md").write_text(text)
    (tmp_path / "runs").mkdir()
    for name, env in runs.items():
        (tmp_path / "runs" / f"{name}.json").write_text(json.dumps(env))
    monkeypatch.setattr(grade, "HERE", tmp_path)
    return sorted((tmp_path / "runs").glob("*.json"))


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def test_a_run_stamped_with_the_current_arm_is_neither_stale_nor_unstamped(tmp_path, monkeypatch):
    arm = "# policy\n"
    files = _bank(tmp_path, monkeypatch,
                  {"1-S-1": {"result": "", "arm": "S", "arm_sha256": _sha(arm)}},
                  {"S": arm})
    _, stale, unstamped = grade.arm_provenance(files)
    assert stale == [] and unstamped == []


def test_a_run_made_against_a_different_arm_is_reported_stale(tmp_path, monkeypatch):
    """The failure this exists for. The arms were built 2026-08-19 22:29 and SKILL.md moved
    the next morning; the only thing linking a run to its arm was a comment telling you to
    move runs/ aside, and it went stale the same day it was written."""
    files = _bank(tmp_path, monkeypatch,
                  {"1-S-1": {"result": "", "arm": "S", "arm_sha256": _sha("# yesterday\n")}},
                  {"S": "# today, with a new quick-nav table\n"})
    _, stale, unstamped = grade.arm_provenance(files)
    assert stale == ["1-S-1"]
    assert unstamped == []


def test_an_unstamped_run_is_not_reported_as_stale(tmp_path, monkeypatch):
    """Runs banked before stamping cannot be verified either way. Calling them stale would be
    asserting something unknown, and the 63 runs carrying the published figure are all of
    them -- reporting those as wrong would be a louder error than the one being fixed."""
    files = _bank(tmp_path, monkeypatch,
                  {"1-S-1": {"result": ""}}, {"S": "# today\n"})
    _, stale, unstamped = grade.arm_provenance(files)
    assert stale == []
    assert unstamped == ["1-S-1"]


def test_a_damaged_envelope_does_not_break_the_provenance_check(tmp_path, monkeypatch):
    """result_text already reports damage. Raising here would lose the whole report over one
    truncated file."""
    files = _bank(tmp_path, monkeypatch, {}, {"S": "# today\n"})
    (tmp_path / "runs" / "1-S-1.json").write_text("{not json")
    files = sorted((tmp_path / "runs").glob("*.json"))
    _, stale, unstamped = grade.arm_provenance(files)
    assert stale == [] and unstamped == []


def test_provenance_is_checked_per_arm_not_globally(tmp_path, monkeypatch):
    """C, S and P are three different files. A stale S must not implicate a current C."""
    c, s = "# empty\n", "# policy\n"
    files = _bank(tmp_path, monkeypatch, {
        "1-C-1": {"result": "", "arm": "C", "arm_sha256": _sha(c)},
        "1-S-1": {"result": "", "arm": "S", "arm_sha256": _sha("# old S\n")},
    }, {"C": c, "S": s})
    _, stale, unstamped = grade.arm_provenance(files)
    assert stale == ["1-S-1"]
