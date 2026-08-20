"""Tests for validate.sh's target detection and its version floor.

The other half of claude-skills-gm0. validate.sh runs `terragrunt` and `terraform`, so an
end-to-end test would only pass on a machine that has both and would not run in CI. What IS
testable without either is the part that decides WHICH commands to run, and that is where the
consequential mistakes live:

  * A multi-unit tree read as `single` runs the checks in the root only, reports a pass, and
    never looks at the units. A green run over nothing is the worst outcome this script has.
  * A root-only directory read as `single` runs unit commands with no unit, so every check
    fails for a reason that has nothing to do with the configuration.

The functions are extracted and sourced rather than the whole script being sourced, because
validate.sh calls `main` unconditionally at the bottom. The extraction asserts it found the
function, so a rename fails loudly here rather than silently testing nothing.
"""

import pathlib
import re
import subprocess

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "validate.sh"


def extract(func: str) -> str:
    body = re.search(rf"^{func}\(\) \{{.*?^\}}", SCRIPT.read_text(), re.S | re.M)
    assert body, f"{func}() is not in validate.sh under that name -- the test, or the rename, is wrong"
    return body.group(0)


def target_mode(tmp_path: pathlib.Path) -> str:
    harness = f'TARGET_DIR="{tmp_path}"\n{extract("detect_target_mode")}\ndetect_target_mode\n'
    out = subprocess.run(["bash", "-c", harness], capture_output=True, text=True, check=True)
    return out.stdout.strip()


def test_a_directory_with_nothing_in_it_is_none(tmp_path):
    assert target_mode(tmp_path) == "none"


def test_a_lone_terragrunt_hcl_is_a_single_unit(tmp_path):
    (tmp_path / "terragrunt.hcl").write_text("")
    assert target_mode(tmp_path) == "single"


def test_a_lone_stack_file_is_also_a_single_target(tmp_path):
    """terragrunt.stack.hcl is the 1.x stack entry point and is as much a target as a unit."""
    (tmp_path / "terragrunt.stack.hcl").write_text("")
    assert target_mode(tmp_path) == "single"


def test_nested_units_make_it_multi_even_with_a_config_at_the_root(tmp_path):
    """The dangerous direction. Read as `single`, the run checks the root and reports a pass
    while never opening a unit."""
    (tmp_path / "terragrunt.hcl").write_text("")
    (tmp_path / "prod").mkdir()
    (tmp_path / "prod" / "terragrunt.hcl").write_text("")
    assert target_mode(tmp_path) == "multi"


def test_a_root_hcl_alone_is_root_only_not_a_unit(tmp_path):
    """root.hcl is the 1.x root config and is included BY units; it is not one. Running unit
    commands here fails for reasons unrelated to the configuration."""
    (tmp_path / "root.hcl").write_text("")
    assert target_mode(tmp_path) == "root-only"


def test_the_module_cache_does_not_turn_a_single_unit_into_a_stack(tmp_path):
    """.terragrunt-cache holds a copy of every downloaded module, each with its own
    terragrunt.hcl. Counting those makes every unit look like a multi-unit tree, and the run
    then walks other people's modules."""
    (tmp_path / "terragrunt.hcl").write_text("")
    cache = tmp_path / ".terragrunt-cache" / "abc123" / "mod"
    cache.mkdir(parents=True)
    (cache / "terragrunt.hcl").write_text("")
    assert target_mode(tmp_path) == "single"


# ------------------------------------------------------------------ the version floor

@pytest.mark.parametrize("line,pre_1_0", [
    ("terragrunt version 1.1.3", False),
    ("terragrunt version 1.0.0", False),
    ("terragrunt version v0.99.9", True),
    ("terragrunt version v0.93.0", True),
])
def test_the_floor_is_1_0_0_not_0_93(line, pre_1_0):
    """This script gated on 0.93 until 2026-08-20 -- a pre-1.0 floor inside a skill whose
    first hard policy bans pre-1.0 forms. Every command it runs (`hcl fmt`, `hcl validate`,
    `run --all`, `dag graph`) is a post-1.0 name that does not exist on 0.x."""
    harness = f'''
        tg_version="{line}"
        if [[ "$tg_version" =~ [^0-9]([0-9]+)\\.([0-9]+)\\.([0-9]+) ]]; then
            if (( BASH_REMATCH[1] < 1 )); then echo PRE; else echo OK; fi
        else echo UNPARSED; fi
    '''
    out = subprocess.run(["bash", "-c", harness], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == ("PRE" if pre_1_0 else "OK")


def test_the_version_gate_in_the_script_matches_the_one_tested_here():
    """The test above runs a copy of the gate. This asserts the copy is still the original --
    without it, the gate could be reverted to 0.93 and these tests would keep passing."""
    text = SCRIPT.read_text()
    assert "BASH_REMATCH[1] < 1" in text, "the 1.0 floor is gone from validate.sh"
    assert "minor_version < 93" not in text, "the 0.93 floor is back in validate.sh"


def test_the_script_no_longer_advertises_a_pre_1_0_target():
    """Nine places said '0.93+'. They are user-facing: the banner, --help, and three warnings
    a user reads when something has already gone wrong."""
    text = SCRIPT.read_text()
    advertised = [ln for ln in text.splitlines()
                  if "0.93" in ln and not ln.lstrip().startswith("#")]
    assert advertised == [], f"still tells the user 0.93: {advertised}"
