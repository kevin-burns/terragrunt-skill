"""Tests for the cross-model runner and the bank isolation that keeps it honest.

The cross-model arm is ADDITIVE. Its whole value depends on its results never being mistaken
for, pooled with, or quoted in place of the Claude measurement, so the things tested here are
the ones that would make that happen quietly:

  * a run written into runs/, which is the Claude bank
  * two models' hits sharing a hit id and so inheriting each other's verdict
  * the control arm silently acquiring a system prompt it is defined not to have

Nothing here reaches the network: `call` takes an injectable opener.
"""

import importlib.util
import io
import json
import pathlib
import urllib.error

import pytest

EVALS = pathlib.Path(__file__).resolve().parent.parent / "evals"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rm = _load("run_model", EVALS / "run_model.py")
grade = _load("grade", EVALS / "grade.py")


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ok(payload):
    return lambda req: _Resp(json.dumps(payload).encode())


# --------------------------------------------------------------------- envelope

def test_envelope_matches_the_shape_grade_py_already_reads():
    """The reason this arm is cheap: the graders are regex over text and do not know which
    model wrote it. That only holds while the envelope keys match run.sh's."""
    env = rm.envelope({
        "model": "google/gemini-3.7-flash",
        "choices": [{"message": {"content": "terragrunt run --all plan"}}],
        "usage": {"cost": 0.0031, "prompt_tokens": 12},
    })
    assert env["result"] == "terragrunt run --all plan"
    assert env["total_cost_usd"] == pytest.approx(0.0031)


def test_envelope_survives_a_response_with_no_choices():
    """A refusal, a filter or a zero-length completion returns no choices. Raising here would
    lose the cell; recording an empty result lets grade.py report it as excluded, which is
    visible. A silently-passing empty run is the failure mode that cost nine cells before."""
    env = rm.envelope({"choices": [], "usage": {}})
    assert env["result"] == ""
    assert env["total_cost_usd"] == 0.0


def test_cost_comes_from_the_provider_not_a_local_price_table():
    """Prices move -- gemini-3.7-flash was half price under a temporary discount on
    2026-08-20. A hardcoded rate would report a number that was true last week."""
    assert rm.envelope({"choices": [], "usage": {"cost": 0.42}})["total_cost_usd"] == 0.42


# --------------------------------------------------------------------- the arms

def test_the_control_arm_sends_no_system_message_at_all():
    """run.sh omits --append-system-prompt entirely for the control rather than passing an
    empty string. An empty system message is still a system message and is not the same
    experiment."""
    assert rm.build_messages("", "write a terragrunt.hcl") == [
        {"role": "user", "content": "write a terragrunt.hcl"}
    ]
    assert rm.build_messages("   \n\n", "x")[0]["role"] == "user"


def test_a_non_empty_arm_becomes_the_system_message():
    msgs = rm.build_messages("# Hard policy\n1. Post-1.0 CLI only.", "write a terragrunt.hcl")
    assert msgs[0]["role"] == "system"
    assert "Post-1.0 CLI only" in msgs[0]["content"]
    assert msgs[1]["role"] == "user"


# --------------------------------------------------------------------- bank isolation

def test_the_runner_refuses_to_write_into_the_claude_bank(tmp_path, monkeypatch):
    """The refusal must fire BEFORE the arm and case files are looked for. arms/ is gitignored,
    so a version of this test that reached the arm check first passed here and failed in CI,
    where no arms exist -- and it would have let a real `--out-dir runs` through on any machine
    that had not built the arms yet."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "not-a-real-key")
    with pytest.raises(SystemExit) as e:
        rm.main(["--model", "x/y", "--arm", "C", "--case", "1", "--rep", "1",
                 "--out-dir", "runs"])
    assert "refusing to write into runs/" in str(e.value)


def test_the_default_out_dir_is_named_for_the_model():
    assert rm.slug("google/gemini-3.7-flash") == "google-gemini-3.7-flash"
    assert rm.slug("openai/gpt-oss-20b:free") == "openai-gpt-oss-20b-free"


def test_two_banks_never_share_a_hit_id():
    """Same case, arm, rep and snippet from two different models. Sharing an id would make
    one model's adjudicated verdict silently apply to the other's output."""
    args = ("1", "C", "1", "run-all", "terragrunt run-all plan")
    a = grade.hit_id(*args, bank="runs-google-gemini-3.7-flash")
    b = grade.hit_id(*args, bank="runs-openai-gpt-oss-20b-free")
    assert a != b


def test_the_claude_banks_hit_ids_did_not_move():
    """245 verdicts are recorded against these ids. The default bank must contribute nothing
    to the hash, or every one of them is orphaned."""
    args = ("1", "C", "1", "run-all", "terragrunt run-all plan")
    assert grade.hit_id(*args) == grade.hit_id(*args, bank="runs")


# --------------------------------------------------------------------- retries

def test_a_rate_limit_is_retried_and_a_bad_request_is_not():
    calls = []

    def flaky(req):
        calls.append(1)
        if len(calls) < 3:
            raise urllib.error.HTTPError(rm.ENDPOINT, 429, "slow down", {}, io.BytesIO(b"{}"))
        return _Resp(json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode())

    out = rm.call("x/y", [], 10, "k", sleep=lambda s: None, opener=flaky)
    assert out["choices"][0]["message"]["content"] == "ok"
    assert len(calls) == 3

    def bad(req):
        raise urllib.error.HTTPError(rm.ENDPOINT, 400, "bad model", {}, io.BytesIO(b"{}"))

    with pytest.raises(SystemExit) as e:
        rm.call("x/y", [], 10, "k", sleep=lambda s: None, opener=bad)
    assert "400" in str(e.value)


def test_a_missing_key_names_the_file_to_source_and_never_the_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(SystemExit) as e:
        rm.api_key()
    assert "env.sh" in str(e.value)
