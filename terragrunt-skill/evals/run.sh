#!/usr/bin/env bash
# One cell of the policy-compliance matrix: run.sh <arm C|S|P> <case id> <replicate n>
# Writes runs/<case>-<arm>-<n>.json
#
# NO --json-schema, deliberately. Lesson 1 of evals/ablation/README.md: a forced schema
# overrides output shape, and this suite grades the CLI and HCL the model actually emits.
# Constraining the shape would be measuring the harness.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ARM="$1"; CASE="$2"; REP="$3"
# RUNS_DIR lets a check run into its own bank instead of overwriting the one carrying the
# published figure. Default is the canonical bank, so nothing changes unless asked.
RUNS_DIR="${RUNS_DIR:-runs}"
OUT="$HERE/${RUNS_DIR}/${CASE}-${ARM}-${REP}.json"

ARMFILE="$HERE/arms/${ARM}.md"
CASEFILE="$HERE/cases/${CASE}.txt"
[ -f "$ARMFILE" ]  || { echo "no arm $ARM -- run: uv run evals/build_arms.py" >&2; exit 1; }
[ -f "$CASEFILE" ] || { echo "no case $CASE" >&2; exit 1; }

mkdir -p "$HERE/${RUNS_DIR}"

# Empty sandbox cwd with every file and search tool disallowed. Nothing on disk for any arm
# to discover, so no arm can read back the references it was never given -- and the control
# arm cannot find a terragrunt.hcl lying around and infer the house style from it.
SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT

ARGS=(
  -p
  --model sonnet
  --safe-mode
  --no-session-persistence
  --output-format json
  --disallowed-tools "Bash" "Read" "Write" "Edit" "Glob" "Grep" "WebFetch" "WebSearch" "Agent" "Task"
  --max-budget-usd 0.60
)

# An empty arm file means the CONTROL arm: no system prompt is appended at all.
if [ -s "$ARMFILE" ]; then
  ARGS+=(--append-system-prompt "$(cat "$ARMFILE")")
fi

# Write to a private temp file and move it into place, so a cell is either absent or complete.
# Writing straight to $OUT means an orphaned process from a killed matrix and a fresh one can
# share the path: the result is a valid envelope, a prose fragment, and a second envelope in
# one file. That happened to 9 of 63 cells on 2026-08-19 and the grader read them as empty.
TMP="$(mktemp "${OUT}.partial.XXXXXX")"
cd "$SANDBOX"
env -u ANTHROPIC_API_KEY claude "${ARGS[@]}" "$(cat "$CASEFILE")" > "$TMP" 2>"$OUT.err" </dev/null || true

# STAMP THE ARM THIS RUN WAS ACTUALLY GIVEN. Until 2026-08-20 the only thing standing between
# a banked run and the arm it was compared against was a COMMENT in matrix.sh telling you to
# move runs/ aside when SKILL.md moves. It went stale the same day it was written: the arms
# were built at 22:29 and SKILL.md moved the next morning, and nothing said a word. A hash in
# the envelope turns that instruction into something grade.py can check.
python3 - "$TMP" "$ARMFILE" "$ARM" <<'STAMP'
import hashlib, json, pathlib, sys
tmp, armfile, arm = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
raw = tmp.read_text()
try:
    env = json.loads(raw)
except json.JSONDecodeError:
    sys.exit(0)          # leave a damaged envelope alone; grade.py reports it as damaged
env["arm"] = arm
env["arm_sha256"] = hashlib.sha256(armfile.read_bytes()).hexdigest()
tmp.write_text(json.dumps(env) + "\n")
STAMP

mv -f "$TMP" "$OUT"
echo "$OUT"
