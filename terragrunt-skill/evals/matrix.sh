#!/usr/bin/env bash
# Full matrix: 7 cases x 3 arms x 3 replicates = 63 runs, 3 at a time.
#
# THREE REPLICATES IS THE FLOOR, not a budget choice. Lesson 3 of the ablation README: a
# between-arm difference is unreadable without knowing how much two runs of the SAME arm
# differ. grade.py reports that noise floor beside every result.
#
# Select a subset with env vars:
#   CASES="1 5" ARMS="C S" REPS="1 2 3" ./matrix.sh
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# Default is the canonical bank. Set RUNS_DIR to check something without
# overwriting the runs that carry the published figure.
RUNS_DIR="${RUNS_DIR:-runs}"

# SMOKE=1 is the cheap default for "did I break it": the two cases carrying the most signal,
# every arm, one replicate. 6 runs. Case 1 (run-all) has the largest control effect; case 3
# (validate-inputs) is the ONLY case where arm P differs from arm S, so between them they catch
# both a broken skill and a broken ban.
if [ "${SMOKE:-0}" = "1" ]; then
  CASES="${CASES:-1 3}"; ARMS="${ARMS:-C S P}"; REPS="${REPS:-1}"
else
  CASES="${CASES:-1 2 3 4 5 6 7}"; ARMS="${ARMS:-C S P}"; REPS="${REPS:-1 2 3}"
fi

# MEASURED 2026-08-20 across 108 banked runs: control $0.053/run, skill arms $0.15/run.
# A full matrix is 63 cells (~$7.63); with the negative cases 108 (~$13.08). That is easy to
# trigger by accident, so anything above MAX_CELLS refuses unless CONFIRM=1. Re-running the
# full matrix should be a decision, not a reflex -- and note the arms carry SKILL.md ONLY, so
# a change to a reference file cannot move these numbers and does not warrant a re-run at all.
MAX_CELLS="${MAX_CELLS:-24}"
n_cells=0
for c in $CASES; do for a in $ARMS; do for r in $REPS; do n_cells=$((n_cells+1)); done; done; done
est=$(awk -v n="$n_cells" -v arms="$(echo "$ARMS" | wc -w)" 'BEGIN{printf "%.2f", n*0.121}')
echo "planned: $n_cells cells  (~\$$est at measured rates)"
if [ "$n_cells" -gt "$MAX_CELLS" ] && [ "${CONFIRM:-0}" != "1" ]; then
  echo "REFUSING: $n_cells cells exceeds MAX_CELLS=$MAX_CELLS." >&2
  echo "  cheap check:  SMOKE=1 ./evals/matrix.sh          (6 cells, ~\$0.73)" >&2
  echo "  full run:     CONFIRM=1 ./evals/matrix.sh        (~\$$est)" >&2
  echo "  Existing cells are skipped, so a resume costs only what is missing." >&2
  exit 2
fi

n=0
for c in $CASES; do
  for a in $ARMS; do
    for r in $REPS; do
      out="$HERE/${RUNS_DIR}/${c}-${a}-${r}.json"
      # Lesson 5: a banked result is silently reused. Move runs/ aside whenever SKILL.md
      # has moved, or this will compare today's arm against last week's answer.
      [ -s "$out" ] && { echo "skip $c-$a-$r"; continue; }
      RUNS_DIR="$RUNS_DIR" "$HERE/run.sh" "$a" "$c" "$r" &
      n=$((n+1))
      if [ $((n % 3)) -eq 0 ]; then wait; fi
    done
  done
done
wait
written=("$HERE/$RUNS_DIR"/*.json)
[ -e "${written[0]}" ] || written=()
echo "matrix complete: ${#written[@]} result files in $RUNS_DIR/"
