"""Tests for the banner generator.

The banner shows a terragrunt version. That is a pin baked into an image, and an image is a
worse place for one than prose: it cannot be grepped, and nobody re-reads a picture. SKILL.md
made exactly this mistake in words -- "current stable v1.1.2" expired within a fortnight while
the binary on the author's own machine was already 1.1.3 -- so the banner is generated from
`terragrunt --version` rather than typed.

What is tested is the boundary between what rots and what does not. `v1.1.0+ autoinclude` is a
fact about WHEN A FEATURE LANDED and stays literal in the template; the transcript line and the
newest hazard are filled in. Getting that split wrong in either direction is the failure: too
few placeholders and the image goes stale, too many and durable facts start moving every
release for no reason.
"""

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("mb", ROOT / "scripts" / "make_banner.py")
mb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mb)

REAL = """terragrunt 1.1.3

SAFE TO EMIT -- gates this build satisfies:
  v1.1.0+  (GA, no experiment needed)
      - autoinclude block; unit.<name>.path / stack.<name>.path references

UPGRADE HAZARDS already in effect on this build:
  ! 1.1.3: --filter now reserves ( and ) for the bounded-discovery boundary operand, and the
  reservation applies whether or not the experiment is enabled.
"""


# ------------------------------------------------------------------ reading the binary

def test_the_version_comes_from_preflight_not_from_the_template():
    assert mb.fields(REAL)["VERSION"] == "1.1.3"


def test_a_newer_binary_changes_the_transcript_line():
    out = mb.fields(REAL.replace("terragrunt 1.1.3", "terragrunt 1.2.0"))
    assert out["VERSION"] == "1.2.0"


def test_output_with_no_version_is_refused_rather_than_guessed():
    """The one thing this script must never do is invent a version. That is the failure it
    exists to prevent."""
    with pytest.raises(SystemExit):
        mb.fields("terragrunt is not installed\n")


def test_a_build_with_no_hazards_is_a_state_not_an_error():
    out = mb.fields("terragrunt 1.1.3\n\nSAFE TO EMIT -- gates this build satisfies:\n")
    assert out["HAZARD_VERSION"] == "1.1.3"
    assert "no upgrade hazards" in out["HAZARD_TEXT"]


# ------------------------------------------------------------------ fitting one line

def test_the_hazard_is_cut_to_its_first_clause():
    """The full hazard is a paragraph; the banner row is one line in a fixed-width box. The
    reference file is where the detail belongs."""
    assert mb.fields(REAL)["HAZARD_TEXT"] == "--filter now reserves ( and )"


def test_a_long_hazard_is_truncated_rather_than_overflowing_the_window():
    """Silently running past the window edge would be invisible in a diff and obvious in the
    published image."""
    long = ("terragrunt 1.4.0\n\nUPGRADE HAZARDS already in effect on this build:\n"
            "  ! 1.4.0: " + "x" * 200 + "\n")
    text = mb.fields(long)["HAZARD_TEXT"]
    assert len(text) <= mb.HAZARD_CHARS
    assert text.endswith("…")


# ------------------------------------------------------------------ the template contract

def test_every_placeholder_in_the_template_gets_a_value():
    """A placeholder with no value would ship as a literal {{VERSION}} in the image."""
    svg = mb.render(mb.fields(REAL))
    assert "{{" not in svg
    assert ">1.1.3<" in svg          # the version lands in its own tspan
    assert "--filter now reserves ( and )</tspan>" in svg


def test_a_template_placeholder_with_no_value_is_refused():
    with pytest.raises(SystemExit) as e:
        mb.render({"VERSION": "1.1.3"})
    assert "no value" in str(e.value)


def test_the_durable_gate_facts_are_not_placeholders():
    """v1.1.0+ and v1.1.1+ say WHEN a feature landed. Those do not rot, and turning them into
    placeholders would make them move every release for no reason."""
    tmpl = mb.TMPL.read_text()
    assert "v1.1.0+" in tmpl
    assert "v1.1.1+" in tmpl
    assert "autoinclude" in tmpl


def test_the_committed_banner_carries_no_leftover_placeholder():
    """A hand-edited banner.svg is how the mirror would ship an image that no longer matches
    its template. This is the cheap half of that check; `make_banner.py --check` is the other
    half and needs a terragrunt on PATH, which CI does not have."""
    committed = mb.SVG.read_text()
    assert "{{" not in committed


def test_the_committed_banner_shows_a_version_shaped_token():
    import re
    committed = mb.SVG.read_text()
    shown = committed.split('terragrunt </tspan><tspan fill="#71BD86">')[1].split("<")[0]
    assert re.fullmatch(r"\d+\.\d+\.\d+\S*", shown), f"banner shows {shown!r}, not a version"
