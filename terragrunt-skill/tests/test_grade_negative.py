"""Tests for the negative-case grader's over-reach detection.

The whole suite rests on one distinction: a Terragrunt construct in PROSE is correct (case 10
asks outright whether to adopt Terragrunt), while the same construct in a CODE BLOCK is
unasked-for scaffolding. If that line moves, the suite measures nothing.

The dangerous false positive is `terraform { required_providers ... }` — a legitimate Terraform
settings block that appears correctly in case 8, and which differs from Terragrunt's
`terraform { source = ... }` only by its contents.
"""

import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "gn", pathlib.Path(__file__).resolve().parent.parent / "evals" / "grade_negative.py"
)
gn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gn)


def names(text):
    return sorted({n for n, _ in gn.overreach(text)})


# --- the prose / code-block line -------------------------------------------------------------

def test_construct_in_prose_is_not_overreach():
    text = ("You could put this in a Terragrunt unit with an `include \"root\"` block and let "
            "`find_in_parent_folders()` resolve the path, but for 200 lines it is not worth it.")
    assert names(text) == []


def test_same_construct_in_a_code_block_is_overreach():
    text = '''Here you go:

```hcl
include "root" {
  path = find_in_parent_folders("root.hcl")
}
```
'''
    assert "include block" in names(text)


def test_case_10_correct_answer_scores_clean():
    """Recommending AGAINST adoption discusses Terragrunt heavily and emits no config."""
    text = ("Short answer: no, not yet. Terragrunt earns its keep when you have repeated "
            "configuration across environments — remote_state duplicated per directory, the "
            "same module wired up five times. With one directory, one environment and one "
            "person, `include` blocks and `dependency` wiring are overhead with nothing to "
            "amortise them against. Revisit when you add a second environment.")
    assert names(text) == []


# --- the false positive that would break the metric -------------------------------------------

def test_terraform_settings_block_is_not_terragrunt():
    """`terraform { required_providers }` is ordinary Terraform and is CORRECT in case 8."""
    text = '''```hcl
terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}
```'''
    assert "terraform.source" not in names(text)


def test_terragrunt_terraform_block_with_source_is_overreach():
    text = '''```hcl
terraform {
  source = "git::ssh://git@github.com/acme/modules.git//s3?ref=v1.0.0"
}
```'''
    assert "terraform.source" in names(text)


def test_a_plain_terraform_resource_block_is_clean():
    text = '''```hcl
resource "aws_s3_bucket" "this" {
  bucket = var.name
}

variable "name" { type = string }
output "arn" { value = aws_s3_bucket.this.arn }
```'''
    assert names(text) == []


def test_terraform_import_answer_is_clean():
    """Case 12's correct answer names the import command and no Terragrunt config."""
    text = '''```bash
terraform import aws_s3_bucket.this my-existing-bucket
```'''
    assert names(text) == []


# --- the individual constructs -----------------------------------------------------------------

def test_detects_each_terragrunt_only_construct():
    for snippet, expected in [
        ('remote_state {\n  backend = "s3"\n}', "remote_state block"),
        ('dependency "vpc" {\n  config_path = "../vpc"\n}', "dependency block"),
        ('generate "provider" {\n  path = "p.tf"\n}', "generate block"),
        ('unit "app" {\n  source = "../x"\n}', "unit/stack block"),
        ('path = find_in_parent_folders("root.hcl")', "find_in_parent_folders"),
        ('key = "${path_relative_to_include()}/tofu.tfstate"', "path_relative_*"),
        ('terragrunt run --all -- plan', "run --all"),
    ]:
        assert expected in names(f"```hcl\n{snippet}\n```"), expected


def test_multiple_blocks_are_all_scanned():
    text = ("```bash\necho hi\n```\n\nand then\n\n"
            '```hcl\nremote_state {\n  backend = "s3"\n}\n```')
    assert "remote_state block" in names(text)


def test_unfenced_code_is_not_scanned():
    """Only fenced blocks count. Indented pseudo-code in prose is discussion, not delivery."""
    assert names("    include \"root\" {\n      path = find_in_parent_folders()\n    }") == []


def test_every_case_has_a_why():
    """The report prints a reason per case; a blank would make the output useless."""
    for c in gn.NEGATIVE_CASES:
        assert gn.WHY.get(c, "").strip(), c


def test_source_must_be_a_direct_child_of_the_terraform_block():
    """Known, deliberate limitation: `source` after a nested block inside a Terragrunt
    `terraform {}` is missed. That ordering is unusual, and a false negative is much safer
    than wrongly accusing a correct Terraform answer of over-reach."""
    missed = '''```hcl
terraform {
  extra_arguments "common" { commands = ["plan"] }
  source = "../../modules/vpc"
}
```'''
    assert "terraform.source" not in names(missed)
