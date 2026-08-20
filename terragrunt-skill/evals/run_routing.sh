#!/usr/bin/env bash
# One cell of the ROUTING suite: run_routing.sh <arm C|S|P> <case id> <replicate n>
# Writes runs-routing/<case>-<arm>-<n>.jsonl (the raw stream) alongside a .json envelope.
#
# HOW THIS DIFFERS FROM run.sh, and why both exist.
#
# run.sh inlines an arm into --append-system-prompt and DISALLOWS Read, Grep and Glob, so no
# arm can reach what it was stripped of. That isolates SKILL.md cleanly, which is what makes
# the published figure readable -- and it makes two things unmeasurable. The ten reference
# files (~31,000 words) are unreachable, so nothing says whether they are any good. And
# routing cannot be asked at all: the skill is always on, so "did the agent open the right
# reference" has no meaning when there is no file to open.
#
# This runner materialises the arm ON DISK and allows the read tools. The leak is prevented by
# WHAT IS ON DISK, not by removing the tools -- disallowing Read was a blunt instrument that
# also deleted the thing worth measuring.
#
# THE FIVE CONTROLS, each load-bearing:
#   1. ALLOWLIST *AND* AN EXPLICIT DENY ON BASH. The design for this suite said an allowlist
#      was the safer choice because a denylist is only as good as the list. THAT IS WRONG, and
#      the very first real run proved it: with --allowed-tools "Read" "Grep" "Glob" and nothing
#      else, the agent called Bash five times and read
#      ~/.claude/skills/terragrunt-skill/references/cli-reference.md -- the author's REAL
#      installed skill, outside the sandbox. --allowed-tools does not restrict what may run.
#      --disallowed-tools is the mechanism that does, which is what run.sh has always used.
#   2. Bash stays out BY NAME. It is the escape hatch -- `cat /Users/...` and `sed -n` walk
#      around every other control, and both were observed doing exactly that.
#   3. NEVER --add-dir. Default scope is cwd, and --add-dir is exactly how the real repo would
#      get exposed by accident.
#   4. The sandbox is a fresh mktemp -d per cell, removed on exit.
#   5. stream-json output, so every tool call and its file path is recorded. grade_routing.py
#      turns that into a CHECK: any read outside the sandbox discards the run, loudly.
#
# IT CONFOUNDS ROUTING WITH CONTENT. A bad answer here does not say which failed. That is why
# the inlined suite stays: this is a third suite beside it, never a replacement.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ARM="$1"; CASE="$2"; REP="$3"
RUNS_DIR="${RUNS_DIR:-runs-routing}"
OUT="$HERE/${RUNS_DIR}/${CASE}-${ARM}-${REP}.jsonl"

ARMDIR="$HERE/arms-disk/${ARM}"
CASEFILE="$HERE/cases/${CASE}.txt"
[ -d "$ARMDIR" ]   || { echo "no on-disk arm $ARM -- run: uv run evals/build_arms.py --on-disk" >&2; exit 1; }
[ -f "$CASEFILE" ] || { echo "no case $CASE" >&2; exit 1; }

mkdir -p "$HERE/${RUNS_DIR}"

SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT
# Arm C copies nothing, so its sandbox is genuinely empty. An empty skill/ directory would be
# a visible thing for the agent to find and reason about, which is not the same as absence.
cp -R "$ARMDIR"/. "$SANDBOX"/ 2>/dev/null || true

ARGS=(
  -p
  --model sonnet
  --safe-mode
  --no-session-persistence
  --output-format stream-json
  --verbose
  --allowed-tools "Read" "Grep" "Glob"
  --disallowed-tools "Bash"
  --max-budget-usd 0.60
)

# The arm is not a system prompt here -- it is the filesystem. The only instruction is to look.
# Arm C gets the same instruction and finds nothing, which is the control: same prompt, same
# tools, no skill.
# DO NOT MAKE THE AGENT DISCOVER THE SKILL. The first attempt asked it to look for ./skill,
# and one run globbed "./skill/SKILL.md", got "No files found" from the leading ./, gave up,
# and answered as the control -- emitting run-all. That is variance in DISCOVERY, which this
# suite is not measuring and which does not happen in the product, where the skill is injected.
# Name the path. What is being measured is whether it then routes to the right reference.
#
# Arm C gets the identical instruction and finds nothing, which is the control: same prompt,
# same tools, no skill.
PREAMBLE="Read the file skill/SKILL.md, then follow its router to whichever reference file it
names for this task and read that too, before answering. If skill/SKILL.md does not exist,
answer from what you already know."

TMP="$(mktemp "${OUT}.partial.XXXXXX")"
cd "$SANDBOX"
env -u ANTHROPIC_API_KEY claude "${ARGS[@]}" \
  "$PREAMBLE

$(cat "$CASEFILE")" > "$TMP" 2>"$OUT.err" </dev/null || true

# Record the sandbox path and the arm hash. The path is what grade_routing.py checks every
# read against; without it a leak cannot be distinguished from a legitimate in-sandbox read.
python3 - "$TMP" "$SANDBOX" "$ARM" "$ARMDIR" <<'STAMP'
import hashlib, json, os, pathlib, sys
tmp, sandbox, arm, armdir = sys.argv[1], sys.argv[2], sys.argv[3], pathlib.Path(sys.argv[4])
h = hashlib.sha256()
for f in sorted(p for p in armdir.rglob("*") if p.is_file()):
    h.update(str(f.relative_to(armdir)).encode())
    h.update(f.read_bytes())
# REALPATH, not the raw mktemp -d value. On macOS mktemp returns /var/folders/... while the
# agent sees the resolved /private/var/folders/..., and a prefix check against the unresolved
# form flags every in-sandbox read as a leak. The first run of the grader did exactly that.
meta = {"_meta": True, "arm": arm, "arm_sha256": h.hexdigest(),
        "sandbox": os.path.realpath(sandbox), "sandbox_raw": sandbox}
with open(tmp, "a") as fh:
    fh.write(json.dumps(meta) + "\n")
STAMP

mv -f "$TMP" "$OUT"
echo "$OUT"
