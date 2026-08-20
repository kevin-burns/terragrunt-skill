# Recorded results

## 2026-08-19 — baseline, before the post-eval fixes

Banked as `runs-2026-08-19-baseline.tar.gz` (63 envelopes + hits.jsonl).

Measured against **SKILL.md blob `7fb92c4c`**, repo `802600b4`, i.e. BEFORE the quick-navigation
table was added and before the `hcl-blocks.md` retry-block defect below was fixed. Anything
quoted from this run must be quoted against that version.

| arm | | runs with >=1 pre-1.0 form | mean per run |
|---|---|---|---|
| C | control, no skill | **81%** (17/21) | 4.71 |
| P | SKILL.md minus the ban | 38% (8/21) | 1.05 |
| S | full SKILL.md | **24%** (5/21) | 0.29 |

*Re-graded 2026-08-19 after two grader defects were fixed (below). The first pass read
90% / 48% / 29% and 4.86 / 1.24 / 0.38. Every arm fell, and the ratio between control and
skill WIDENED from 12.8x to 16.2x — the fixes removed false violations, and there were
proportionally more of them in the arms that carry the skill.*

63 runs, 3 replicates, $8.34. No errored runs.

**The null hypothesis is rejected.** Unaided, the model emits a pre-1.0 Terragrunt form in
nine runs out of ten.

**Both halves of the skill contribute.** P sitting between C and S is the point of having a
third arm: correct 1.x context alone takes 4.86 -> 1.24, and stating the ban explicitly takes
it the rest of the way to 0.38. Two arms could not have separated those.

### Caveats, both load-bearing

**Replicate noise floor is 48%** — 10 of 21 case x arm cells disagree with themselves across
replicates. It ROSE from 33% when the grader was fixed, which is expected and not a
regression: removing false violations pushed several cells down to 0-or-1, and a cell
straddling zero flips more easily than one at four. Per-case numbers are NOT readable at this
floor. The arm-level gap — 81% against 24%, 57 points — is several times it and is.

**All 218 hits are unadjudicated.** The advisory/violation split above is the regex guess.
`grade.py --final` refuses to report until a human has read them.

### A grader defect this run exposed

Case 6 appeared to show the skill not helping (C=6, S=5, P=5). It is a false positive:
`retryable_errors` is a VALID attribute inside the 1.x `errors { retry {} }` block, and the
regex cannot tell it from the banned top-level attribute. A second false positive: "not the
old `hclvalidate`" was scored a violation because the weak-signal pattern requires
`old (form|syntax|name|command|way)` and the word was followed by a backtick.

BOTH ARE NOW FIXED and the banked envelopes re-graded. `grade.py` gained a third verdict
class, `valid-1x`, for a form that is legal inside an enclosing block, and it looks backwards
up to 400 chars for that block before condemning a hit. 10 of the 218 hits reclassify this way.
Both fixes are pinned in tests/test_eval_grade.py (40 tests).

Case 6 after the fix reads C=3 S=3 P=1 rather than C=6 S=5 P=5. The skill still does not
visibly help on `retryable_errors` — but case 6 is now unstable across all three arms, so that
reading is below the noise floor and must not be reported as a finding.

### A skill defect this run exposed

Chasing case 6 found that `references/hcl-blocks.md` documents three pre-1.0 retry
constructs as current, with no version caveat -- `## BLOCK: retry_max_attempts` (568),
`## BLOCK: retry_sleep_interval_sec` (589), `## BLOCK: retryable_errors` (610) -- and
documents no `## BLOCK: errors` at all, so the 1.x replacement is missing from the block
reference entirely. Meanwhile SKILL.md bans `retryable_errors` and
`architecture-patterns.md:276` says never to emit it. The skill contradicts itself, in a file
whose header declares it was harvested from a source last updated five weeks before
Terragrunt 1.0.

### Re-run policy

Do NOT re-run cell by cell as fixes land. Land them all, then move `runs/` aside, rebuild all
three arms, and run the full matrix once. $8.34 and about ten minutes.


---

## 2026-08-19 — second run, after the reference fixes

Banked as `runs-2026-08-19-postfix.tar.gz`. Measured against **SKILL.md blob 83720637**
(baseline was 7fb92c4c; the file grew 16,063 -> 19,634 chars via the quick-nav table, the
rewritten Provenance, the CI/CD router entry and the terraform-registry hand-off).

| arm | | runs with >=1 pre-1.0 form | mean per run |
|---|---|---|---|
| C | control, no skill | **95%** (20/21) | 6.81 |
| P | SKILL.md minus the ban | 43% (9/21) | 1.05 |
| S | full SKILL.md | **19%** (4/21) | 0.24 |

63 runs, all valid, $9.13. Noise floor 38% (8/21 cells).

### THE MOST USEFUL RESULT IS NOT IN THE TABLE

**The control arm moved, and the control arm did not change.** Arm C is an empty file: no
system prompt, same seven cases, same three replicates, same model. Between the two runs it
went from 81% to 95% of runs emitting a pre-1.0 form, and from 4.71 to 6.81 mean violations
per run — a 45% increase in an arm that is byte-for-byte identical.

So a single measurement of any one arm is worth very little. What survives both runs is the
GAP, and only at low precision:

  the model unaided emits a pre-1.0 form in ROUGHLY EIGHT TO NINE RUNS IN TEN
  with the skill, ROUGHLY TWO IN TEN

Quote it that way. Do NOT publish "81%" or "95%" as though either were the number, and do not
publish a ratio (16x on the first run, 28x on the second) — the ratio is the least stable
statistic here because it divides by a small, noisy denominator.

### What the fixes did and did not affect

The four defects fixed between the runs (c3x, cun) were in REFERENCE files. The arms carry
SKILL.md only, so the arms could not see them. Any movement between the runs is SKILL.md's 22%
growth plus run-to-run variance, and the control's behaviour shows variance alone is large
enough to account for it. **This pair of runs does not measure whether the reference fixes
helped.** Nothing here can, because the harness cannot reach the references.

### Still outstanding

247 hits unadjudicated. `grade.py --final` refuses to report until they are read.

---

## 2026-08-19 — ADJUDICATED. SUPERSEDED 2026-08-20 — see the last section.

> These were the numbers to quote until the skill changed under them. Kept in full because the
> movement between this bank and the 2026-08-20 one is itself the argument for never quoting a
> percentage.

All 239 distinct hits read by a human. `grade.py --final` exits 0.

| arm | | runs with >=1 pre-1.0 form | mean per run |
|---|---|---|---|
| C | control, no skill | **19 of 21** | 6.86 |
| P | SKILL.md minus the ban | 4 of 21 | 0.71 |
| S | full SKILL.md | **1 of 21** | 0.05 |

Adjudication moved S from 4/21 to 1/21 and C from 20/21 to 19/21, and dropped the replicate
noise floor from 38% to 24% — most of the instability was classifier error, not model variance.

### How to state this in public

**Say:** unaided, the model reached for a pre-1.0 Terragrunt form in NINETEEN OF TWENTY-ONE
runs. With the skill, in ONE. — **NO LONGER TRUE. The current bank says SEVENTEEN of
twenty-one. Use that.** Everything else in this subsection still holds.

**Do not say** 90% and 5%. Two runs of the identical control arm produced 81% and 95% on the
same day (see the two runs above), so the third significant figure is noise. **Do not publish a
ratio** — it divides by a denominator of one.

**Do not claim the skill "works 95% of the time".** This measures ONE property: whether a
banned CLI form appears. An answer can score clean and still be wrong.

### The finding that was not expected

**87% of arm P's violations (13 of 15) are in a single case: `validate-inputs`.**

Arm P is the skill with hard-policy item 1 removed. Without the ban it still gets `run-all`,
`hclfmt`, bare `find_in_parent_folders()` and `skip` right — 0 violations on all four. It fails
almost exclusively on `validate-inputs`.

The likely reason is structural: the other four forms have 1.x replacements shown REPEATEDLY
throughout SKILL.md's own text, so the correct form is crowded in even with the prohibition
gone. `validate-inputs` is the one banned form that appears NOWHERE ELSE in SKILL.md. The ban
is the only thing standing against it.

If that holds, the mechanism is "show the right form everywhere" more than "list the forbidden
ones" — and the ban earns its place specifically where no positive example exists. That is a
lead, not a law: it rests on 13 violations across 2 runs, and case 3 arm P is one of the five
unstable cells.

### What remains untestable here

The arms carry SKILL.md only. The references (~31,000 words) are unreachable because the
harness disallows Read and Grep, so nothing in this suite measures reference quality, the
version gates, or diagnosis accuracy.

---

## 2026-08-19/20 — the NEGATIVE suite, cases 8-12

Five prompts where Terragrunt config is NOT the answer: a Terraform module (8), Kubernetes (9),
whether to adopt Terragrunt for a 200-line single-environment config (10), HCL dynamic blocks
(11), importing an existing resource (12). 45 runs, 3 arms, 3 replicates.

### Signal 1 — unasked-for scaffolding: NULL ON EVERY ARM

| arm | runs | runs emitting Terragrunt config in a code block |
|---|---|---|
| C | 15 | 0 |
| S | 15 | 0 |
| P | 15 | 0 |

**Report this as a null, not as a pass.** Arm C is also zero — the model does not emit
unasked-for scaffolding even with NO skill installed — so these cases cannot separate the arms
on this axis. The correct reading is "the skill does not INTRODUCE over-reach", and the cases
were too easy to have detected it if it did. Strengthening them means prompts where over-reach
is genuinely tempting: a question that is 80% a Terragrunt question with a non-Terragrunt
answer, not one that is plainly out of scope.

The suite still earns its place. Without it the positive suite measures eagerness as if it were
accuracy — a skill answering everything with scaffolding would score 100% there.

### Signal 2 — pre-1.0 vocabulary while merely DISCUSSING Terragrunt

The same runs carry a different measure, and this one is not null. **No config was requested in
any of these cases.** Adjudicated by reading all six hits:

| arm | runs | runs using a pre-1.0 name |
|---|---|---|
| C | 15 | **3** |
| S | 15 | **0** |
| P | 15 | 1 |

**All three control violations are the same thing: `run-all`, in all three replicates of case
10** — a prompt that asks whether to adopt Terragrunt and requests no code at all.

  10-C-1  "orchestrated `apply`/`destroy` ordering (`run-all`)"
  10-C-2  "orchestrating `run-all` across a dependency graph of modules"
  10-C-3  "generating shared `backend`/`provider` blocks and running `run-all`"

Not warnings, not "the old form" — the pre-1.0 name presented as the feature's name. So the
training-data prior shows up in VOCABULARY, not only in generated config, and it is consistent
rather than occasional: 3 of 3.

The two `find_in_parent_folders()` hits (10-S-1, 10-P-2) are generic mentions of the function in
a list of things a reader would have to learn — adjudicated advisory. The one real P violation
is 12-P-1 recommending `--terragrunt-non-interactive`.

### The advice, read by hand

The grader cannot see whether the ADVICE is right, so case 10 was read. Both the control and
the skill arm correctly answer **no** — "one directory, one environment, one person… there's
nothing to DRY up". The skill does not make the model recommend itself, which was the failure
mode worth checking and is the reason this case exists.

---

## READ THIS BEFORE QUOTING `grade.py` OUTPUT

`grade.py` scans **every case it finds in `runs/`**, which is now 12 — the seven positive cases
AND the five negative ones. Its summary therefore prints a POOLED figure:

    C 22/36   S 1/36   P 5/36

**That is not the headline and must not be published.** The negative cases (8–12) are prompts
where nobody expects a violation, so pooling them inflates the denominator and dilutes the
effect. The number for the post is computed over **cases 1–7 only**:

    C 19/21   S 1/21   P 4/21

**Superseded on 2026-08-20** by a re-run against the shipping skill — see the last section of
this file. The current figure is **C 17/21   S 1/21   P 3/21**. The shape of the argument is
unchanged; the control number moved by two runs.

To reproduce it, restrict the scan:

```bash
uv run evals/grade.py --cases 1,2,3,4,5,6,7 --final
```

`grade.py` gained that filter on 2026-08-20, and it now leads its report with the bank and the
case list it is summarising, warning outright when they are not the published set:

    BANK: runs/   CASES: 1,2,3,4,5,6,7   RUNS: 63

Running it without `--cases` still pools all twelve and still prints a real number. It is just
answering a question nobody asked, and it looks enough like the headline to be quoted in its
place — which is why the header now says which one you are looking at.

All 245 hits across all 12 cases in THAT bank were adjudicated; `--final` exited 0.

---

## 2026-08-20 — RE-RUN AGAINST THE SHIPPING SKILL. These supersede everything above.

The re-run the "Re-run policy" section above asked for. Everything before this point was
measured against SKILL.md as it stood on 2026-08-19; SKILL.md has changed six times since
(#28–#36). The old bank is preserved as `runs-2026-08-20-pre-full-rerun.tar.gz`.

108 fresh runs (12 cases × 3 arms × 3 replicates), no errored runs, $9.04 for the seven
publishable cases. **Every envelope carries `arm` and `arm_sha256`** — the first bank that
does. Arm S is `12b794ddd2ed`, P is `2a8a1bfe82f3`, C is the empty string. All 234 hits read
and adjudicated by hand; `grade.py --cases 1,2,3,4,5,6,7 --final` exits 0.

| arm | | runs with ≥1 pre-1.0 form | violations | mean per run |
|---|---|---|---|---|
| C | control, no skill | **17 / 21** | 113 | 5.38 |
| P | SKILL.md minus the ban | 3 / 21 | 16 | 0.76 |
| S | full SKILL.md | **1 / 21** | 1 | 0.05 |

**Replicate noise floor: 2 of 21 cells (10%)** — the lowest yet, down from 24% on the
adjudicated 2026-08-19 bank. Only `case 4 arm S` and `case 7 arm C` disagree with themselves.
The arm-level gap is far above it.

### How to state this in public — UPDATED, the old sentence is now wrong

> Unaided, the model reached for a pre-1.0 Terragrunt form in **seventeen of twenty-one runs**.
> With the skill, in **one**.

Not nineteen. The 2026-08-19 bank said nineteen and that sentence is in
`claude-skills-xfw.15`; it was true of that bank and is not true of this one. The whole two-run
difference is the control getting *better*: case 5 arm C went 3/3 violating to **0/3** (it
reached for the 1.x `exclude` block unprompted, all three times), and case 7 rep 1 named the
`--terragrunt-` flags only to call them deprecated aliases.

That movement is the argument for the standing rules, not against them: **still never a
percentage** (81% here, 81% and 90% on 2026-08-19, 95% on a smoke the same day) and **still
never a ratio** (denominator of one).

### The unexpected finding got sharper

On the 2026-08-19 bank, 87% of arm P's violations were case 3 (`validate-inputs`). On this
bank it is **16 of 16 — every single one**. Without the explicit ban, the skill's surrounding
1.x context is enough to hold `run-all`, `hclfmt`, `skip`, `retryable_errors`, bare
`find_in_parent_folders` and the `--terragrunt-` flags at **zero violations each**. Only
`validate-inputs` gets through.

`validate-inputs` remains the one banned form with no positive counter-example anywhere else in
SKILL.md. Every other ban has a 1.x replacement shown somewhere in the file; there is nothing
to show for this one, because 1.x removed the capability rather than renaming it. The mechanism
looks more like *show the right form everywhere* than *list the forbidden ones* — and where
there is no right form to show, only the list is holding the line.

### The one S violation, in full

Case 4, replicate 3. The answer's own code block used `find_in_parent_folders("root.hcl")`
correctly, then a bullet below it offered:

    include "envcommon" { path = "${dirname(find_in_parent_folders())}/_envcommon/service.hcl" }

Bare, in emitted config. Every other S-arm mention of a banned form across 21 runs is prose
naming it to warn against it, or `retryable_errors` legitimately inside `errors { retry {} }`.

### Negative suite, cases 8–12: unchanged

Null on every arm — 0 unasked-for constructs in all 45 runs. Report as "does not introduce
over-reach", never as a pass. Pre-1.0 vocabulary while merely discussing Terragrunt:
C 3/15, S 0/15, P 0/15 (auto-classified; the S and P zeros have nothing to adjudicate).
