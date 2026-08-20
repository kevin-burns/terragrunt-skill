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
OUT="$HERE/runs/${CASE}-${ARM}-${REP}.json"

ARMFILE="$HERE/arms/${ARM}.md"
CASEFILE="$HERE/cases/${CASE}.txt"
[ -f "$ARMFILE" ]  || { echo "no arm $ARM -- run: uv run evals/build_arms.py" >&2; exit 1; }
[ -f "$CASEFILE" ] || { echo "no case $CASE" >&2; exit 1; }

mkdir -p "$HERE/runs"

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
mv -f "$TMP" "$OUT"
echo "$OUT"
