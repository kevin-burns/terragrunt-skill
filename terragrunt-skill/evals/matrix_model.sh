#!/usr/bin/env bash
# The CROSS-MODEL matrix, via OpenRouter: matrix_model.sh <model-id>
#
# ADDITIVE, NEVER A SUBSTITUTE. This does not re-measure the Claude result and cannot replace
# it -- a different model is a different prior. It answers a different question: does the
# effect come from what the skill SAYS, or is it a Claude-specific quirk? Results land in
# runs-<model-slug>/ and are graded separately:
#
#   source ~/.config/dotfiles/env.sh          # OPENROUTER_API_KEY is not in a non-interactive shell
#   ./evals/matrix_model.sh google/gemini-3.7-flash
#   uv run evals/grade.py --runs-dir runs-google-gemini-3.7-flash --cases 1,2,3,4,5,6,7
#
# READ THE CONTROL ARM FIRST. A model too weak to write Terragrunt emits no banned forms and
# scores as a clean pass. If arm C is also clean, that model is not exercising the thing being
# measured -- drop it from the panel rather than reporting it. Same rule that made the
# over-reach suite a null.
#
# PICK FOR PROVENANCE DIVERSITY, NOT PRICE. Three cheap models from one lab are weaker
# evidence than one each from three labs.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

MODEL="${1:-}"
[ -n "$MODEL" ] || { echo "usage: matrix_model.sh <openrouter-model-id>" >&2; exit 2; }
[ -n "${OPENROUTER_API_KEY:+set}" ] || {
  echo "OPENROUTER_API_KEY is not set. source ~/.config/dotfiles/env.sh" >&2; exit 2; }

# SMOKE first: setting the defaults before reading it makes ${CASES:-1 3} a no-op, so the
# smoke run quietly becomes a full matrix. matrix.sh gets this order right; this did not.
if [ "${SMOKE:-0}" = "1" ]; then
  CASES="${CASES:-1 3}"; ARMS="${ARMS:-C S P}"; REPS="${REPS:-1}"
else
  CASES="${CASES:-1 2 3 4 5 6 7}"; ARMS="${ARMS:-C S P}"; REPS="${REPS:-1 2 3}"
fi

SLUG="$(printf '%s' "$MODEL" | tr -c '[:alnum:].-' '-')"
OUT_DIR="${OUT_DIR:-runs-$SLUG}"

n_cells=0
for c in $CASES; do for a in $ARMS; do for r in $REPS; do n_cells=$((n_cells+1)); done; done; done
echo "model:   $MODEL"
echo "bank:    $OUT_DIR/"
echo "planned: $n_cells cells"
echo
echo "Per-key spend is capped by OpenRouter itself, so a runaway loop cannot exceed the"
echo "limit on the key. Check what is left before a large run:"
echo "  curl -s -H \"Authorization: Bearer \$OPENROUTER_API_KEY\" https://openrouter.ai/api/v1/key"
echo

# run_model.py is stdlib only, so a bare python3 is enough -- no uv, no pip, no venv.

n=0
for c in $CASES; do
  for a in $ARMS; do
    for r in $REPS; do
      out="$HERE/$OUT_DIR/${c}-${a}-${r}.json"
      # Same lesson as matrix.sh: a banked result is silently reused. Move the bank aside
      # whenever SKILL.md has moved, or this compares today's arm against last week's answer.
      [ -s "$out" ] && { echo "skip $c-$a-$r"; continue; }
      python3 "$HERE/run_model.py" --model "$MODEL" --arm "$a" --case "$c" --rep "$r" \
        --out-dir "$OUT_DIR" || echo "FAILED $c-$a-$r" >&2
      n=$((n+1))
    done
  done
done
written=("$HERE/$OUT_DIR"/*.json)
[ -e "${written[0]}" ] || written=()
echo "done: ${#written[@]} result files in $OUT_DIR/"
