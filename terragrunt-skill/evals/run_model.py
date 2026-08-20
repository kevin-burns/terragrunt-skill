#!/usr/bin/env python3
"""One cell of the CROSS-MODEL arm, via OpenRouter.

WHY THIS EXISTS, and what it is not. The banked Claude measurement answers "does this skill
change what Claude writes". It cannot answer "does the effect come from what the skill SAYS,
or from a Claude-specific quirk". Running the same arms and cases through models from other
labs answers that, and it is the strongest single sentence the write-up can carry.

IT IS ADDITIVE, NEVER A SUBSTITUTE. A different model is a different prior, so these runs
cannot be pooled with the Claude ones and cannot stand in for them. That is enforced
structurally: --out-dir defaults to runs-<model-slug>/ and NOTHING writes into runs/, which
is the Claude bank. grade.py --runs-dir grades one directory at a time.

THE TRAP, and the thing to check before reporting anything. A model too weak to write
Terragrunt at all emits no banned forms and scores as a clean pass. The CONTROL arm is the
detector: if arm C is also clean for a model, that model is not writing Terragrunt and belongs
out of the panel, not in the result. Same rule that turned the over-reach suite into a null.

Pick the panel for PROVENANCE DIVERSITY, not price. Three cheap models from one lab are
weaker evidence than one each from three labs.

The key is read from OPENROUTER_API_KEY and never echoed. Source ~/.config/dotfiles/env.sh
first -- it is absent from non-interactive shells.

Usage:
    python3 run_model.py --model google/gemini-3.7-flash --arm C --case 1 --rep 1
    python3 run_model.py --model x/y --arm S --case 3 --rep 1 --out-dir runs-x-y
"""

import argparse
import hashlib
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
ARMS = ("C", "S", "P")

# Generous but bounded. The cases ask for a config file, not an essay, and an unbounded
# completion on a per-token-priced model is how a cheap matrix stops being cheap.
DEFAULT_MAX_TOKENS = 4096
# Retried statuses. 429 is rate limiting, which the free tiers do constantly.
RETRY_STATUS = (408, 429, 500, 502, 503, 504)


def slug(model: str) -> str:
    """google/gemini-3.7-flash -> google-gemini-3.7-flash. Used for the output directory,
    so two models can never share a bank."""
    return "".join(c if c.isalnum() or c in ".-" else "-" for c in model)


def api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise SystemExit(
            "OPENROUTER_API_KEY is not set. Source it first:\n"
            "    source ~/.config/dotfiles/env.sh\n"
            "It is absent from non-interactive shells."
        )
    return key


def build_messages(arm_text: str, case_text: str) -> list[dict]:
    """An EMPTY arm file is the control: no system message at all, matching run.sh, which
    omits --append-system-prompt entirely rather than passing an empty string."""
    messages = []
    if arm_text.strip():
        messages.append({"role": "system", "content": arm_text})
    messages.append({"role": "user", "content": case_text})
    return messages


def call(model: str, messages: list[dict], max_tokens: int, key: str,
         attempts: int = 4, sleep=time.sleep, opener=None) -> dict:
    """Returns the parsed OpenRouter response. `sleep` and `opener` are injectable so the
    tests never reach the network."""
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        # Ask for the real charge rather than deriving one from a price table that drifts.
        "usage": {"include": True},
    }).encode()
    req = urllib.request.Request(
        ENDPOINT, data=payload, method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # OpenRouter attributes traffic by these; they are public repo URLs, not secrets.
            "HTTP-Referer": "https://github.com/kevin-burns/claude-skills",
            "X-Title": "terragrunt-skill eval",
        },
    )
    send = opener or (lambda r: urllib.request.urlopen(r, timeout=180))
    last = ""
    for attempt in range(attempts):
        try:
            with send(req) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:400]
            last = f"HTTP {e.code}: {body}"
            if e.code not in RETRY_STATUS:
                raise SystemExit(f"{model}: {last}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = f"{type(e).__name__}: {e}"
        if attempt < attempts - 1:
            sleep(2 ** attempt)
    raise SystemExit(f"{model}: gave up after {attempts} attempts -- {last}")


def envelope(resp: dict) -> dict:
    """The shape grade.py already reads: a `result` string and `total_cost_usd`. Reusing it
    is the whole reason this arm is cheap -- the graders are regex over text and do not know
    or care which model produced it."""
    choices = resp.get("choices") or []
    text = ""
    if choices:
        text = (choices[0].get("message") or {}).get("content") or ""
    usage = resp.get("usage") or {}
    return {
        "result": text,
        "total_cost_usd": float(usage.get("cost") or 0.0),
        # Kept for provenance. `model` is what OpenRouter actually served, which is not
        # always what was asked for -- a :free variant can be routed to a different provider.
        "model": resp.get("model"),
        "usage": usage,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    p.add_argument("--model", required=True, help="OpenRouter model id, e.g. google/gemini-3.7-flash")
    p.add_argument("--arm", required=True, choices=ARMS)
    p.add_argument("--case", required=True)
    p.add_argument("--rep", required=True)
    p.add_argument("--out-dir", default=None,
                   help="default runs-<model-slug>/ -- NEVER runs/, which is the Claude bank")
    p.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    args = p.parse_args(argv)

    # THE DESTINATION IS CHECKED FIRST, before the inputs exist. This is a safety guard, not a
    # precondition: someone who typos --out-dir runs should be told THAT, whatever else is
    # missing. It also keeps the guard testable anywhere -- arms/ is gitignored, so a test
    # that reached the arm check first passed locally and failed in CI, where no arms exist.
    out_dir = HERE / (args.out_dir or f"runs-{slug(args.model)}")
    if out_dir.resolve() == (HERE / "runs").resolve():
        raise SystemExit(
            "refusing to write into runs/ -- that is the Claude bank, and pooling a "
            "different model's runs with it would corrupt the published measurement."
        )

    armfile = HERE / "arms" / f"{args.arm}.md"
    casefile = HERE / "cases" / f"{args.case}.txt"
    if not armfile.is_file():
        raise SystemExit(f"no arm {args.arm} -- run: uv run evals/build_arms.py")
    if not casefile.is_file():
        raise SystemExit(f"no case {args.case}")

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{args.case}-{args.arm}-{args.rep}.json"

    arm_text = armfile.read_text()
    resp = call(args.model, build_messages(arm_text, casefile.read_text()),
                args.max_tokens, api_key())
    env = envelope(resp)
    # Same stamp run.sh writes. A banked run has to carry the arm it was actually given, or
    # nothing can tell it apart from one made against a different SKILL.md.
    env["arm"] = args.arm
    env["arm_sha256"] = hashlib.sha256(armfile.read_bytes()).hexdigest()

    # Same lesson as run.sh: write private, then rename. A cell is either absent or complete,
    # never a half-written file that the grader reads as an empty -- which scores as a pass.
    tmp = out.with_suffix(".json.partial")
    tmp.write_text(json.dumps(env, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out)
    print(f"{out}  ${env['total_cost_usd']:.4f}  {len(env['result'])} chars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
