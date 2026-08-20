#!/usr/bin/env bash
# The ROUTING matrix. Third suite, beside the inlined one — never a replacement for it.
#
#   uv run evals/build_arms.py --on-disk    # arms-disk/<arm>/ must exist first
#   SMOKE=1 ./evals/matrix_routing.sh       # 4 cells
#   CONFIRM=1 ./evals/matrix_routing.sh     # the full set
#   uv run evals/grade_routing.py
#
# ARMS DEFAULT TO "C S", NOT "C S P", and that is a design decision rather than a saving.
# Arm P is "SKILL.md minus the ban". Once references/ is on disk and readable, hcl-blocks.md
# still says retryable_errors was removed in 1.0 and cli-reference.md still carries the 1.x
# command tree — so the ban leaks straight back in and the ablation does not ablate. Set
# ARMS="C S P" deliberately if you want to ask "does removing it from SKILL.md matter when the
# references are reachable", which is a real but DIFFERENT question. The C/S/P comparison that
# produces the published figure stays with the inlined arms.
#
# MEASURED 2026-08-20: ~$0.15 a cell, against ~$0.12 for an inlined one. It takes more turns —
# reading the skill, then a reference — so budget MORE replicates here, not fewer: extra turns
# mean extra variance, and this suite is noisier than the one it sits beside.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
RUNS_DIR="${RUNS_DIR:-runs-routing}"

if [ "${SMOKE:-0}" = "1" ]; then
  CASES="${CASES:-1 4}"; ARMS="${ARMS:-C S}"; REPS="${REPS:-1}"
else
  CASES="${CASES:-1 2 3 4 5 6 7 8 9 10}"; ARMS="${ARMS:-C S}"; REPS="${REPS:-1 2 3}"
fi

[ -d "$HERE/arms-disk" ] || {
  echo "no arms-disk/ — run: uv run evals/build_arms.py --on-disk" >&2; exit 2; }

MAX_CELLS="${MAX_CELLS:-24}"
n_cells=0
for c in $CASES; do for a in $ARMS; do for r in $REPS; do n_cells=$((n_cells+1)); done; done; done
est=$(awk -v n="$n_cells" 'BEGIN{printf "%.2f", n*0.15}')
echo "planned: $n_cells cells  (~\$$est at measured rates)  bank: $RUNS_DIR/"
if [ "$n_cells" -gt "$MAX_CELLS" ] && [ "${CONFIRM:-0}" != "1" ]; then
  echo "REFUSING: $n_cells cells exceeds MAX_CELLS=$MAX_CELLS." >&2
  echo "  cheap check:  SMOKE=1 ./evals/matrix_routing.sh" >&2
  echo "  full run:     CONFIRM=1 ./evals/matrix_routing.sh   (~\$$est)" >&2
  exit 2
fi

n=0
for c in $CASES; do
  for a in $ARMS; do
    for r in $REPS; do
      out="$HERE/${RUNS_DIR}/${c}-${a}-${r}.jsonl"
      # Same trap as the other matrices: a banked result is silently reused. The arm hash in
      # each envelope is what makes a stale one detectable rather than a comment asking nicely.
      [ -s "$out" ] && { echo "skip $c-$a-$r"; continue; }
      RUNS_DIR="$RUNS_DIR" "$HERE/run_routing.sh" "$a" "$c" "$r" >/dev/null || echo "FAILED $c-$a-$r" >&2
      n=$((n+1))
      if [ $((n % 3)) -eq 0 ]; then wait; fi
    done
  done
done
wait
written=("$HERE/$RUNS_DIR"/*.jsonl)
[ -e "${written[0]}" ] || written=()
echo "routing matrix complete: ${#written[@]} result files in $RUNS_DIR/"
