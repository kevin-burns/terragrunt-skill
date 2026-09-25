import importlib.util
from pathlib import Path

# No pyproject.toml pythonpath config in this skill, so the script is loaded by path --
# keeps the test file self-contained without a sys.path edit or an import-order exemption.
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location("preflight", SCRIPTS_DIR / "preflight.py")
preflight = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(preflight)


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


def test_the_newest_recorded_gate_is_reached_by_its_own_version():
    """Derived from GATES, not pinned. This test used to hardcode 1.1.3 while the comment
    above it claimed nothing here depends on the current release -- so it failed the day
    1.1.4 was added, for no reason except its own pin."""
    newest = preflight.GATES[-1][0]
    out = lines_for(newest)
    assert "SAFE TO EMIT" in out
    assert "DO NOT EMIT" not in out


def test_an_older_build_is_told_what_the_newest_gate_withholds():
    """The inverse, and the one that actually protects a user: the version before the
    newest gate must be told it does not reach it."""
    out = lines_for("1.1.3")
    assert "DO NOT EMIT" in out
    assert preflight.GATES[-1][0] in out.split("DO NOT EMIT")[1]


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


def test_the_cas_depth_hazard_spans_four_releases_and_then_stops():
    """Entered when CAS became the default git path in 1.1.0 and not fixed until 1.1.4.
    It is the longest-lived hazard recorded here, and the one most likely to be read as
    'my module source is wrong' rather than 'my Terragrunt is old'."""
    for version in ("1.1.0", "1.1.1", "1.1.2", "1.1.3"):
        out = lines_for(version)
        assert "depth" in out, version
        assert "invalid repository name" in out, version
    assert "invalid repository name" not in lines_for("1.1.4")


def test_the_cas_local_source_hazard_clears_at_the_same_release():
    assert "source escapes repository root" in lines_for("1.1.2")
    assert "source escapes repository root" not in lines_for("1.1.4")


def test_the_tf_path_fallback_change_is_reported_on_1_1_4():
    """Nothing is enabled and no config changes -- a machine with a broken tofu on PATH
    simply stops working. That is the definition of an upgrade hazard here."""
    out = lines_for("1.1.4")
    assert "UPGRADE HAZARDS" in out
    assert "TG_TF_PATH" in out


def test_the_scaffold_form_change_is_reported_on_1_1_4():
    out = lines_for("1.1.4")
    assert "scaffold" in out
    assert "--non-interactive" in out


def test_the_base64gzip_replacement_is_reported_on_1_1_4_and_cleared_by_1_1_5():
    """Two hazards entered in 1.1.4: one permanent, one fixed a release later. The fixed one
    must stop being reported while the permanent one stays."""
    on_114 = lines_for("1.1.4")
    assert "base64gzip()" in on_114 and "REPLACEMENT" in on_114
    on_115 = lines_for("1.1.5")
    assert "planned replacements" in on_115  # the 1.1.5 gate row explains the fix
    assert "REPLACEMENT" not in on_115
    assert "TG_TF_PATH" in on_115  # the permanent 1.1.4 hazard is still in effect


def test_the_repo_root_change_is_reported_from_1_1_5():
    assert "GIT_DIR" in lines_for("1.1.5")
    assert "GIT_DIR" not in lines_for("1.1.4")


def test_generated_file_permissions_and_flag_precedence_are_reported_on_1_1_5():
    out = lines_for("1.1.6")
    assert "0600" in out
    assert "TERRAGRUNT_LOG_LEVEL" in out


def test_offline_cas_is_withheld_below_1_1_5():
    out = lines_for("1.1.4")
    withheld = out.split("DO NOT EMIT", 1)[1]
    assert "offline-cas" in withheld


def test_a_1_1_x_build_is_warned_about_1_2_without_being_told_to_emit_it():
    """1.2.0 is a release candidate: the plan-visible changes are worth knowing before the
    upgrade, and none of it is a gate."""
    out = lines_for("1.1.6")
    assert "COMING IN 1.2.0" in out and "NOT A GATE" in out
    assert "RootAccess" in out and "base64gzip_compat" in out
    assert "SAFE TO EMIT" in out.split("COMING IN", 1)[0]
    assert "RootAccess" not in out.split("COMING IN", 1)[0]


def test_a_1_2_release_candidate_is_treated_as_unrecorded_not_as_covered():
    """rc1 parses as 1.2.0. It must get the ahead-of-every-gate warning, and the 'coming'
    block must not repeat as if it were still in the future."""
    out = lines_for("terragrunt version v1.2.0-rc1")
    assert "ahead of every gate" in out
    assert "COMING IN" not in out


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
