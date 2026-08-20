import sys
from pathlib import Path

# No pyproject.toml pythonpath config in this skill, so the scripts dir goes on sys.path
# here -- keeps the test file self-contained, same as ghost-publish's suite.
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import preflight  # noqa: E402


def lines_for(version: str) -> str:
    code, lines = preflight.report(version, None)
    assert code == 0, lines
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Gates are facts about history. A build either reaches one or it does not,
# and nothing here depends on what the current release happens to be.
# ---------------------------------------------------------------------------

def test_a_1_0_build_is_told_not_to_emit_the_1_1_0_surface():
    """The whole point of the gate list: 1.0.x must not get autoinclude or CAS attributes."""
    out = lines_for("1.0.5")
    assert "DO NOT EMIT" in out
    blocked = out.split("DO NOT EMIT")[1]
    assert "autoinclude" in blocked
    assert "update_source_with_cas" in blocked


def test_the_installed_generation_reaches_every_recorded_gate():
    out = lines_for("1.1.3")
    assert "SAFE TO EMIT" in out
    assert "DO NOT EMIT" not in out


def test_experiment_gated_features_name_their_flag():
    """A feature that needs an --experiment is useless in this report without the flag name."""
    out = lines_for("1.1.3")
    assert "--experiment mutable-generate" in out
    assert "--experiment block-iteration" in out
    assert "--experiment oci" in out


# ---------------------------------------------------------------------------
# Hazards: the column a version number cannot give you.
# ---------------------------------------------------------------------------

def test_the_filter_parenthesis_hazard_is_reported_on_1_1_3():
    """It breaks a working invocation with nothing enabled, so it has to be loud."""
    out = lines_for("1.1.3")
    assert "UPGRADE HAZARDS" in out
    assert "reserves ( and )" in out


def test_a_fixed_hazard_stops_being_reported_once_you_are_past_the_fix():
    """The iam_role break landed in 1.1.1 and was fixed in 1.1.2. Reporting it forever is
    how a hazard list trains people to skim past the entries that still matter."""
    assert "iam_role" in lines_for("1.1.1")
    assert "iam_role" not in lines_for("1.1.2")
    assert "iam_role" not in lines_for("1.1.3")


def test_a_build_older_than_a_hazard_does_not_see_it():
    assert "iam_role" not in lines_for("1.1.0")


# ---------------------------------------------------------------------------
# Not knowing is a reportable state, not a silent pass.
# ---------------------------------------------------------------------------

def test_a_version_ahead_of_every_gate_warns_rather_than_claiming_coverage():
    """A patch can reserve syntax without enabling anything -- 1.1.3 did exactly that -- so
    an unrecorded version must not be reported as fully understood."""
    out = lines_for("9.9.9")
    assert "WARN" in out
    assert "ahead of every gate" in out


def test_strict_fails_on_an_unrecorded_version_but_the_default_does_not():
    assert preflight.main(["--version", "9.9.9"]) == 0
    assert preflight.main(["--version", "9.9.9", "--strict"]) == 1


def test_an_unparseable_version_fails_rather_than_passing_quietly():
    code, lines = preflight.report("terragrunt: command not found", None)
    assert code == 1
    assert "could not parse" in lines[0]


def test_a_missing_binary_is_a_failure_not_a_warning():
    code, lines = preflight.report("", "terragrunt is not on PATH")
    assert code == 1
    assert lines[0].startswith("FAIL")


def test_the_version_is_found_inside_a_noisy_banner():
    assert preflight.parse("terragrunt version 1.1.3\nbuilt with go1.26.5") == (1, 1, 3)


def test_read_version_surfaces_a_nonzero_exit():
    class Proc:
        returncode, stdout = 3, ""

    def run():
        return Proc()

    raw, err = preflight.read_version(run=run)
    assert "exited 3" in err
