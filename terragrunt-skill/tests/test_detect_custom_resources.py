"""Tests for the custom-resource detector.

This script and validate.sh shipped with NO test of their own. run_ci_checks.sh named that as
a real gap on 2026-08-19 rather than papering over it; this closes half of it
(claude-skills-gm0).

What it is for decides what is worth testing. The detector's output routes a documentation
lookup: a module classified `registry` gets looked up one way, `git` another, and a source
misfiled as `provider` is dropped from the module list entirely. So the classifier and the
official-provider allowlist are the load-bearing parts, and the two failure modes are:

  A CUSTOM PROVIDER READ AS OFFICIAL disappears from the report, and the thing most needing
  a docs lookup is the thing that never gets one.

  AN OFFICIAL PROVIDER READ AS CUSTOM sends the agent hunting for documentation on
  hashicorp/aws, which is noise the report exists to remove.
"""

import importlib.util
import pathlib

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
spec = importlib.util.spec_from_file_location("dcr", SCRIPTS / "detect_custom_resources.py")
dcr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dcr)


@pytest.fixture
def det(tmp_path):
    return dcr.ResourceDetector(str(tmp_path))


# ------------------------------------------------------------------ classification

@pytest.mark.parametrize("source,expected", [
    ("./modules/vpc", "local"),
    ("../../modules/vpc", "local"),
    ("tfr:///terraform-aws-modules/vpc/aws?version=5.0.0", "terragrunt"),
    ("git::https://github.com/org/repo.git//module", "git"),
    ("github.com/org/repo//module", "git"),
    ("git::ssh://git@gitlab.com/org/repo.git", "git"),
    ("https://example.com/module.zip", "http"),
    ("terraform-aws-modules/vpc/aws", "registry"),
    ("Azure/avm-res-network-virtualnetwork/azurerm", "registry"),
])
def test_module_sources_are_categorised_by_how_you_would_look_them_up(det, source, expected):
    assert det._categorize_module_source(source) == expected


def test_a_two_part_source_is_a_provider_not_a_module(det):
    """`hashicorp/aws` and `terraform-aws-modules/vpc/aws` differ only by component count.
    Reading the first as a module puts a provider in the module list and looks up the wrong
    registry; providers are collected separately."""
    assert det._categorize_module_source("hashicorp/aws") == "provider"
    assert det._categorize_module_source("datadog/datadog") == "provider"
    assert det._categorize_module_source("terraform-aws-modules/vpc/aws") == "registry"


def test_the_terragrunt_registry_prefix_is_not_mistaken_for_a_url(det):
    """`tfr:///` is Terragrunt's own registry scheme and resolves through Terragrunt, not
    over HTTP. Classifying it as `http` would send the lookup to a URL that does not exist."""
    assert det._categorize_module_source("tfr:///org/mod/aws") == "terragrunt"


# ------------------------------------------------------------------ the allowlist

def test_an_official_provider_is_not_reported_as_custom(det):
    det._record_custom_provider("hashicorp/aws", "5.0.0")
    det._record_custom_provider("azurerm", "4.1.0")
    assert det.custom_providers == {}


def test_a_third_party_provider_is_reported_with_its_version(det):
    det._record_custom_provider("datadog/datadog", "3.39.0")
    assert det.custom_providers["datadog/datadog"] == {"3.39.0"}


def test_a_provider_pinned_twice_keeps_both_versions(det):
    """Two units on different versions of the same provider is the situation worth surfacing;
    collapsing to one hides a conflict the report exists to find."""
    det._record_custom_provider("datadog/datadog", "3.39.0")
    det._record_custom_provider("datadog/datadog", "3.40.0")
    assert det.custom_providers["datadog/datadog"] == {"3.39.0", "3.40.0"}


def test_an_unpinned_provider_is_recorded_rather_than_dropped(det):
    det._record_custom_provider("datadog/datadog", "")
    assert det.custom_providers["datadog/datadog"] == {"unspecified"}


def test_an_empty_source_is_ignored(det):
    det._record_custom_provider("   ", "1.0.0")
    assert det.custom_providers == {}


# ------------------------------------------------------------------ what it walks

def test_generated_and_vendored_directories_are_not_scanned(tmp_path):
    """.terragrunt-cache holds a COPY of every module the run downloaded. Scanning it reports
    other people's providers as if they were this repo's, and the count grows with every run."""
    (tmp_path / "terragrunt.hcl").write_text("terraform { source = \"./m\" }\n")
    for junk in (".terragrunt-cache", ".terraform", "node_modules", ".git"):
        d = tmp_path / junk / "nested"
        d.mkdir(parents=True)
        (d / "main.tf").write_text("provider \"datadog\" {}\n")

    found = [p.name for p in dcr.ResourceDetector(str(tmp_path)).find_hcl_files()]
    assert found == ["terragrunt.hcl"]


def test_both_hcl_and_tf_files_are_walked(tmp_path):
    (tmp_path / "terragrunt.hcl").write_text("")
    (tmp_path / "main.tf").write_text("")
    (tmp_path / "notes.md").write_text("")
    found = sorted(p.name for p in dcr.ResourceDetector(str(tmp_path)).find_hcl_files())
    assert found == ["main.tf", "terragrunt.hcl"]


# ------------------------------------------------------------------ end to end

def test_a_realistic_tree_reports_the_custom_provider_and_the_module(tmp_path):
    (tmp_path / "terragrunt.hcl").write_text(
        'terraform {\n'
        '  source = "tfr:///terraform-aws-modules/vpc/aws?version=5.0.0"\n'
        '}\n'
    )
    (tmp_path / "providers.tf").write_text(
        'terraform {\n'
        '  required_providers {\n'
        '    aws     = { source = "hashicorp/aws", version = "5.0.0" }\n'
        '    datadog = { source = "DataDog/datadog", version = "3.39.0" }\n'
        '  }\n'
        '}\n'
    )
    det = dcr.ResourceDetector(str(tmp_path))
    det.analyze_directory()
    assert "DataDog/datadog" in det.custom_providers
    assert "hashicorp/aws" not in det.custom_providers


def test_the_json_report_is_parseable(tmp_path):
    """The report is meant to be read by another tool. A report that is only ever eyeballed
    can drift into prose without anyone noticing."""
    import json
    (tmp_path / "main.tf").write_text('provider "datadog" {}\n')
    det = dcr.ResourceDetector(str(tmp_path))
    det.analyze_directory()
    json.loads(det.generate_report(output_format="json"))
