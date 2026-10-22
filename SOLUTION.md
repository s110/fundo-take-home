# Solution

Parts 1 and 2 are built and measured. Part 3 is a plan; its gate is working code. `python3 run.py --offline`
regenerates every number from the committed cache, byte for byte. `EVAL.md` (committed before the first
model run) holds objectives, SLOs and gate thresholds. `DECISIONS.md` gives the reason for each piece.

## 1. Data

Synthetic Plaid `/transactions/get` responses (`fundo/generate.py`). **dev**: 10 businesses, 1,854
transactions, used while I wrote the prompt. **holdout**: 5 businesses, 882 transactions, the same risks
under other names; no change used its results. The cases are those a funder loses money on: a processor's
loan, stacked advances, a funder that writes to the reviewer, a bank with no NSF fees, a loan among small
payouts, family money over Zelle, 61- and 45-day histories, plus 273 hard negatives. The keyword engine
(`fundo/engine.py`) is wrong on purpose: 239 dev labels wrong ($430k), 169 holdout ($173k).

## 2. The reviewer: model proposes, code decides

```
[code] pair own-account transfers → [code] group into patterns (business, direction, template, label;
large credits split off) → [code] remove PII, flag instruction-like text → [model] agree | doubt + group,
business flag, confidence, reason → [code] validate, one retry → [code] policy → [code] revenue
```

- **One call per pattern**, not per transaction: 188 calls for 1,854 dev transactions, and consistent labels.
  No keyword prefilter, because a prefilter is a second keyword list with the same blind spots.
- **Revenue is computed in code**, never by the model. A fooled model cannot set it.
- **Asymmetric policy.** A change that raises the offer needs 0.90; one that lowers it, 0.70; a doubt above
  0.50 goes to a person. While it waits, the cautious label applies. The bars come from Part 2.
- **Untrusted text** reaches the model as `description_untrusted`. A code tripwire also looks for
  instructions. If either fires, a person decides and no change in the business's favour applies.
- **Failures** (invalid JSON twice, outage) keep the keyword label as `unreviewed`. No decision waits.

## 3. Results (Haiku, the incumbent)

| | dev | holdout |
|---|---:|---:|
| wrong labels: keyword → reviewed | 239 → 13 | 169 → 39 |
| over-offer against true labels | $131,045 → $0 | $62,963 → $14,727 (**−77%**) |
| under-offer | $0 → $0 | $0 → $75 |
| hard negatives broken, PII leaks, wrong offer-raising changes | 0, 0, 0 | 0, 0, 0 |

10 dev and 31 holdout "wrong labels" are payouts I labelled `none` and the models call
`revenue_verification`, probably rightly. Both are revenue, and I did not change the truth after seeing
outputs. BO1 (−50% over-offer) holds on the holdout. Its residue is one case: a loan paid under the same text as
daily ClassPay payouts. Every model calls it a payout. The fix (a large credit that stays revenue goes to a
person) is untested, because I found it on the holdout.

## 4. Model choice

Haiku, Sonnet, and DeepSeek Flash with thinking off and on. Same prompt, policy and contract. Each answered
every prompt 3 times (`runs/repeats.md`). Means of 3 samples, holdout:

| | Q1 revenue error | queue / app | cost / app incl. underwriter | gate (dev) |
|---|---:|---:|---:|---|
| Haiku | 9.0 pp | 1.1 | $0.41 | incumbent |
| Sonnet | 8.9 pp | 0.5 | $0.31 | BLOCK |
| DeepSeek, no thinking | 8.9 pp | 0.5 | $0.18 | BLOCK |
| DeepSeek, thinking | 8.9 pp | 0.3 | $0.11 | BLOCK |

**The gate keeps Haiku, but that does not show Haiku is better.**

- **Dev favours Haiku.** I tuned the policy on Haiku's dev replies. Under the policy before that change,
  DeepSeek with thinking beats Haiku on dev (5.9 vs 7.1 pp).
- **One good draw.** Haiku's dev Q1 is 0.0 in the committed run and 3.5 in both new samples.
- **Q1 rests on five patterns.** Q1 is dollars, and each large pattern is 3 to 9 pp, all or nothing. On the
  holdout all four models are equal on quality.
- **Cost separates them.** DeepSeek with thinking queues a quarter as many patterns as Haiku.

A fair choice needs a comparison set that no change has seen, pooled samples and more injection cases. Total
spend: **USD 5.62** at list price.

## 5. Part 2: credit impact

Each `runs/*/*/report.md` gives the features and the offer per business, for keyword, reviewed and true
labels. Sensitivity (`runs/sensitivity.md`, true dev labels, 200 trials per error rate):

| error type | offer change per mislabelled transaction | at 5%: decisions flipped |
|---|---:|---:|
| false revenue | +$3,669 to +$4,371 | 0.6% |
| false NSF | −$275 to −$2,884 | **20.4%** |
| missed NSF | +$2,695 to +$7,188 | 0.9% |
| false / missed active advance | −$340 / +$112 | 0% |

**False revenue vs false advance.** $X of false revenue adds 0.40·X to the offer; $Y of false advance payments
removes 0.31·Y. Similar per dollar, opposite in risk. False revenue makes a business look safer, so Fundo
loses principal. A false advance makes it look riskier, so Fundo loses margin. Hence 0.90 vs 0.70.

**A bank with no NSF fees.** The feature counts fee lines, so it reads 0 and the applicant looks like the
cleanest borrower. In training, it also weakens NSF as a signal for everyone. b05 bounced 7 payments: keyword
labels give 0 NSFs and $40,493, true labels 7 and $0. The reviewer found all 7 from R01 returns. Fix: count
NSF events (fees plus R01/R09 returns), keep a per-bank fee table, send a flagged missing value, not a 0.

**61 days instead of 90.** Dividing by 3 months understates revenue by a third: b10 gets $18,941 instead of
$27,946. NSF counts look better too. The code normalizes revenue by observed days. In production: store
history days, alert under 90, compare with training, and ask for more statements.

## 6. Part 3: production

**Shadow, then a gate.** The reviewer runs on every application, and its output is stored but not used.
Underwriters label a sample stratified by offer impact. Every prompt, model or policy change passes `gate.py`
in CI: hard rules, non-inferiority, superiority on a hidden set before promotion. CI runs the base branch's
gate, so a change cannot loosen its own rules. A transition (for example `none → active_advance`) goes live
when its precision on 200+ labelled cases has a 95% lower bound of 95% (99% if it raises offers).

**Silent drift.** Each run stores which model the provider says it served. The frozen labelled set runs
nightly, because a hosted model can change under its alias. Each risk-model input is compared daily with a
reference window (alert at PSI > 0.2).

**Reproducing a decline after a keyword fix.** Store the raw Plaid response, keyword, prompt and policy
versions, the raw model replies, overrides and features. Replay runs with no model call; here that is
`run.py --offline`, byte-identical in CI.

**Underwriters in the loop.** They review patterns with the reason and offer impact. Their corrections
become keyword fixes, labelled cases for the gate, and per-transition precision.

## 7. Not done, and weaknesses

- **Not done:** Plaid Sandbox (no funder cases), calibration (needs production labels), a truly hidden holdout
  (I wrote both splits), the risk model.
- **Weaknesses:**
  - The tripwire regex is easy to evade, and I wrote the test injections.
  - One answer covers a whole pattern.
  - The gate reads one reply on dev. It pairs runs by the transactions in each pattern, so it cannot compare
    a keyword or data change that groups transactions differently; that change needs a person.
  - Synthetic text is cleaner than real bank text. These numbers test the mechanism, not real quality.

## 8. AI tools used

I built this with Claude Code (an AI coding agent, Claude Opus). It wrote most of the code, the synthetic
data, the prompt and the documents, from my instructions. I set the requirements, the shape of the release gate
(hard rules, non-inferiority, superiority on a hidden set), the models to compare and the budget. The models
under test are the reviewer itself; the coding agent never labelled a transaction.

How it was checked:

- **Contract first.** `EVAL.md` was committed before any model reply (commit `605984a`).
- **A second agent reviewed the code.** It found 10 bugs, fixed in pull request #1. None changed an output.
- **I questioned the results.** Haiku's dev Q1 of 0.0 looked too good. That led to three replies per model
  and the replay of the earlier policy, which showed the dev bias in section 4.

**What is mine is the design.** I can defend each decision and its trade-off: one call per pattern,
revenue in code, the 0.90 and 0.70 bars, the gate margins, and why Haiku stays the incumbent although that
proves little. The rest does not need trust: `python3 run.py --offline` rebuilds every number from the
committed model replies, and CI checks it byte for byte.
