# Policy-compliance eval

Answers one question about `terragrunt-skill`: **does stating the ban change what the model
emits?**

Terragrunt **v1.0.0 shipped 2026-03-30** and renamed much of the CLI. Almost everything
written before that date — the documentation people have bookmarked, blog posts, other
tooling, model training data — describes forms that no longer exist. This skill's first hard
policy bans them outright:

> `run-all`, `plan-all`, `hclfmt`, `hclvalidate`, `graph-dependencies`, `validate-inputs`,
> `terragrunt-` prefixed flags, the `skip` attribute, `retryable_errors`, or bare
> `find_in_parent_folders()`

Nobody had measured whether saying so makes any difference.

## Running it

```bash
uv run evals/build_arms.py     # rebuild all three arms from today's SKILL.md
./evals/matrix.sh              # 7 cases x 3 arms x 3 replicates = 63 runs, 3 at a time
uv run evals/grade.py          # provisional numbers + every hit written to hits.jsonl
uv run evals/grade.py --adjudicate   # read the hits
uv run evals/grade.py --final        # refuses to print until every hit has a verdict
```

### Cost, and the guard

Measured across 108 banked runs on 2026-08-20: **control $0.053/run, skill arms $0.15/run**
(they carry a 19 KB system prompt), **$0.121 average**. So a full matrix is ~$7.63 and the full
set including negatives ~$13.08 — easy to trigger by reflex.

```bash
SMOKE=1 ./evals/matrix.sh      # 6 cells, ~$0.73 — the "did I break it" check
CONFIRM=1 ./evals/matrix.sh    # the full 63, ~$7.63 — a decision, not a reflex
```

`matrix.sh` prints the planned cell count and estimated cost before running, and **refuses
anything over `MAX_CELLS` (default 24) unless `CONFIRM=1`**. Existing cells are skipped, so a
resume costs only what is missing.

SMOKE runs cases **1 and 3** across all three arms, one replicate. Case 1 (`run-all`) has the
largest control-arm effect; case 3 (`validate-inputs`) is the **only** case where arm P differs
from arm S. Between them they catch both a broken skill and a broken ban.

**A reference-file change never warrants a re-run.** The arms carry `SKILL.md` only — the
harness cannot reach `references/`, so nothing in there can move these numbers.

**Do not switch model to save money.** The eval measures what a model reaches for *unaided*;
a different model has a different training-data prior, so changing it is a different experiment
and invalidates comparison with the banked runs. It is also the wrong reader — the skill ships
to people running Claude Code. A local model via Ollama is useful for exercising the HARNESS
(does `run.sh` write atomically, does `grade.py` parse) without spending, not for the
measurement.

Select a subset with `CASES="1 5" ARMS="C S" REPS="1" ./evals/matrix.sh`.

Each run is `claude -p --safe-mode` in an empty sandbox with every file and search tool
disallowed. Measured cost: **$0.04** for a control run; the skill arms carry a ~16 KB system
prompt and cost more. `arms/` and `runs/` are gitignored.

## Two suites, and why the grader now makes you choose

Cases **1–7** are positive: they ask for Terragrunt config, and they carry the published
figure. Cases **8–12** are negative: they ask for plain Terraform, or for advice, and check
the skill does not scaffold Terragrunt nobody asked for.

Pooling them is not wrong, it just answers a question nobody asked — and the pooled figure
looks enough like the headline to be quoted in its place. So `grade.py` prints the bank and
the cases it is reporting on, warns when they are not the published set, and takes a filter:

```bash
uv run evals/grade.py --cases 1,2,3,4,5,6,7 --final    # the published figure
```

## The cross-model arm

`runs/` is the Claude bank and the only thing the headline comes from. A second question sits
beside it: does the effect come from what the skill **says**, or is it a Claude-specific
quirk? Running the same arms and cases through models from other labs answers that, and it is
the strongest single sentence the write-up can carry.

It is cheap because the expensive half is already model-agnostic — the graders are regex over
text and neither knows nor cares which model wrote it. Only the runner is new.

```bash
source ~/.config/dotfiles/env.sh          # OPENROUTER_API_KEY, absent from non-interactive shells
SMOKE=1 ./evals/matrix_model.sh google/gemini-3.7-flash    # 6 cells
./evals/matrix_model.sh google/gemini-3.7-flash            # 63 cells
uv run evals/grade.py --runs-dir runs-google-gemini-3.7-flash --cases 1,2,3,4,5,6,7
```

**It is ADDITIVE, never a substitute.** A different model is a different prior, so these runs
cannot be pooled with the Claude ones and cannot stand in for them. That is enforced rather
than asked for: `run_model.py` refuses `--out-dir runs`, each bank gets its own hits and
adjudications file, and hit ids mix in the bank name so two models cannot inherit each other's
verdicts.

**The trap:** a model too weak to write Terragrunt at all emits no banned forms and scores as
a clean pass. **The control arm is the detector.** If arm C is also clean, that model is not
exercising the thing being measured — drop it from the panel rather than reporting it. Same
rule that turned the negative suite into a null.

**Pick for provenance diversity, not price.** Three cheap models from one lab are weaker
evidence than one each from three labs.

Spend is capped by OpenRouter on the key itself, so a runaway loop cannot exceed it:

```bash
curl -s -H "Authorization: Bearer $OPENROUTER_API_KEY" https://openrouter.ai/api/v1/key
```

## The three arms

| arm | contents | what it isolates |
|---|---|---|
| **C** | empty — no system prompt at all | the null hypothesis: the model on its own |
| **S** | the whole of `SKILL.md` | what ships |
| **P** | `SKILL.md` minus hard-policy item 1 only | everything the skill knows *except* the ban |

**P is why there are three arms and not two.** A gap between C and S on its own is
unreadable: it could be the ban, or it could be that any two thousand words of correct 1.x
Terragrunt context is enough by itself. S − P isolates the ban. C − P isolates the rest.

`build_arms.py` asserts a size decrease, checks that arm P names none of the banned forms and
that arm S names all of them, and fails loudly if hard-policy item 1 has been edited so the
markers no longer match.

## The seven cases

Each is an ordinary engineer's question written to **bait** a pre-1.0 answer without naming
one. If a case mentioned the obsolete form, every arm would score clean by reflex.

| case | bait |
|---|---|
| 1 | plan across thirty modules → `run-all` / `plan-all` |
| 2 | format every `.hcl` in the repo → `hclfmt` |
| 3 | check inputs match the module's variables → `validate-inputs` |
| 4 | child inherits config from the top of the tree → bare `find_in_parent_folders()` |
| 5 | leave one unit out of a whole-tree run → the `skip` attribute |
| 6 | retry transient AWS throttling → `retryable_errors` |
| 7 | point at a directory and config from CI → `--terragrunt-*` flags |

## Why grading is not just a grep

```
"Use `run --all`. (The old `run-all` was removed in 1.0.)"   <- correct
"Run `terragrunt run-all plan`."                             <- the failure
```

Both contain the string. Counting them together would score the skill's own warning as a
violation and could invert the result. So `grade.py` classifies every hit, writes all of them
to `hits.jsonl` with surrounding context, and **`--final` refuses to report until a human has
recorded a verdict for each one** in `adjudications.json`.

The classifier has two tiers. **Strong** signals (`deprecated`, `removed in`, `renamed`,
`superseded`, `pre-1.0`) are rarely incidental and get a ±260-character window. **Weak**
signals (`instead of`, `rather than`, `replaced`) must sit within ±60 characters of the match.

That split was not a design instinct — it was a bug. The first version used one wide window
for everything and misread **8 of 10 hits** in a run that was plainly recommending the forms,
because "instead of" had appeared elsewhere in the answer about something unrelated. A bare
`avoid` was dropped from the list entirely: "avoid interactive prompts" sits one clause from
`--terragrunt-non-interactive` in perfectly ordinary advice, and excused it. Both cases are
pinned in `tests/test_eval_grade.py`.

`skip` and `find_in_parent_folders` need shape rather than a word. `skip` is ordinary English,
so only `skip = true|false` counts; `find_in_parent_folders("root.hcl")` is the **correct** 1.x
call and must never be scored, so only the argument-less form does. Both are tested.

## What this eval cannot tell you

Said here rather than discovered later.

**The ten reference files are not inlined.** `terragrunt-skill` is a router — `SKILL.md` says
which reference to grep, and the references total roughly 31,000 words. The harness disallows
`Read` and `Grep` so no arm can reach them, and inlining all ten would cost a fortune per run
and test an artifact that does not ship. This bounds the effect of **`SKILL.md`**, which is
where the hard policy lives. It says nothing about whether the references are any good.

**It is not a correctness test.** An answer can score clean and still be wrong in ways banned-
form detection cannot see.

**It does not cover version gating.** Whether the skill correctly refuses a v1.1.0+ attribute
for a repo pinned to ≤1.0.x is a separate suite, scoped in `claude-skills-xfw.16`.

**Diagnosis accuracy is out of scope and deliberately so.** Grading whether pasted error text
lands on the right entry among the 68 in `references/error-patterns.md` needs a judge model,
and there is no cloud or backend connected here to produce real error text. If it is ever
built it must run entirely offline against captured strings.

## Rebuild everything when `SKILL.md` moves

`arms/` is gitignored and `matrix.sh` skips any cell whose output already exists. Both are
deliberate, and together they mean a stale arm or a banked run gets silently reused. Comparing
an arm built last week against one built today measures the commit, not the ablation. Rebuild
all three arms and move `runs/` aside whenever the skill has changed.

## Provenance

The ablation method is from Cole Medin's `ablate-ai-layer`
([coleam00/skills](https://github.com/coleam00/skills), MIT). The runner and sandbox setup are
adapted from `evals/ablation/` in this repo, whose README records the five mistakes that
harness made first — the replicate noise floor, leak-checking the assembled text, and
hand-checking every hit before reporting a rate are all inherited from it rather than
rediscovered here.
