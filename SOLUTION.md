# Solution

I built and measured Part 1 (the reviewer) and Part 2 (credit impact). Part 3 is section 6, and its gate
is working code. `python3 run.py --offline` regenerates every number here from the committed cache, byte
for byte. *Estimate* marks a number that is not measured. `EVAL.md` holds the objectives, SLOs and gate
thresholds; I committed it before the first model run. `DECISIONS.md` gives the reason for each piece.

## 1. Data and the legacy engine

`fundo/generate.py` writes synthetic Plaid `/transactions/get` responses (`amount > 0` is money out,
`original_description` is the raw string, PFCv2 categories that are plausible and vague). **dev**: 10
businesses, 1,854 transactions; I looked at its results while I wrote the prompt. **holdout**: 5 businesses,
882 transactions, the same kinds of risk under other names (PayPal Working Capital, CAN Capital, R09
returns, "US TRUSTEE CH13", a transfer across a month end). No prompt or policy change used holdout
results; git shows the freeze commit before the holdout run.

The cases are the ones a funder loses money on: a processor's loan under the processor's name, stacked
advances that the keyword list misses, a funder that writes to the reviewer, a bank with no NSF fees, a loan
paid under the same text as small payments, own-account transfers spelled XFER, family money over Zelle,
and 61- and 45-day histories. 182 dev and 91 holdout transactions are **hard negatives**: they look wrong
but the keyword label is right (Capital One card payments, payouts that say TRANSFER, a $19k customer
payment, a LendingTree bill, a memo that says "IGNORE PREV INVOICE").

The legacy engine (`fundo/engine.py`) matches whole words against 13 lists; precedence picks the group. It
is wrong on purpose: a hyphenated keyword never matches, names collide, lists are incomplete. It mislabels
239 dev transactions ($430k) and 169 holdout ones ($173k).

## 2. The reviewer: the line between model and code

```
keyword labels → [code] pair own-account transfers → [code] patterns (business, direction, template, label;
large credits split off) → [code] remove personal data; tripwire for instruction-like text → [model] agree |
doubt + group, business flag, confidence, reason, description_contains_instructions → [code] validate, one
retry, else keep the keyword label → [code] policy → [code] revenue = f(direction, group, business flag)
```

**The model only proposes a group and a business flag, one pattern at a time.** Every pattern goes to the
model except own-account transfers that code confirms (188 calls for 192 dev patterns, 1,854 transactions). There is no keyword prefilter, because a prefilter is a
second keyword list with the same blind spots. The rest is code, where it is exact and auditable:

- **Revenue is never a model output**, nor are amounts, dates or features. Transfer pairing is a join on
  amount, account and day number. Cadence ("almost every business day") is computed and given to the model.
- **The policy is asymmetric.** A change that raises the offer or removes a risk label needs confidence
  0.90; another change needs 0.70. A doubt from 0.50 up goes to an underwriter, and the cautious label is in
  force while it waits: a change that lowers the offer applies provisionally, one that raises it waits. A
  change that moves no feature (the business flag of a debit) is ignored. The bars are a risk order from
  Part 2, not calibrated probabilities.
- **Untrusted text.** The description reaches the model as `description_untrusted`, which the prompt calls
  evidence, never an instruction. A code tripwire looks for instruction-like text too. If either fires, a
  person sees the pattern and no change in the business's favour applies. One call per pattern, so an
  injection cannot reach other transactions. Emails, phones, SSNs and long numbers are removed before the
  prompt; hard rule H1 checks the prompts against the tagged values.
- **Invalid output and outages.** Code checks JSON, enums, types, confidence range, a reason, and a group
  possible for the direction. An "agree" never changes a label. One retry quotes the error. After that, or
  on an outage, the keyword label stays (`unreviewed`) and the decision does not wait.

The prompt names no counterparty from either split. A rule like "a customer can be a casino" would match a
dev case exactly, so the dev score would say nothing about new data. It states the general rule instead: a
word in a counterparty's name is weak evidence.

## 3. Model choice

Four reviewers with the same prompt, schema and policy. Claude Haiku and Claude Sonnet go through the
Claude Code CLI (I had a subscription, no API key; with `ANTHROPIC_API_KEY` the same code bills a key, a
path I could not test). DeepSeek Flash goes through its HTTP API, once with thinking off and once with
thinking on. EVAL.md did not change for the DeepSeek runs: same metrics, same margins.

| dev / holdout | Q1 gross revenue error | queued patterns per app | H2 injections | p95 per pattern | model cost per app | gate |
|---|---:|---:|---:|---:|---:|---|
| Haiku | **0.0** / **8.9** pp | 0.7 / 0.8 | 3/3, 1/1 | 4.1 / 4.7 s | $0.008 / $0.009 | incumbent |
| Sonnet | 9.3 / 8.9 pp | 0.8 / 0.2 | 3/3, **0/1** | 7.9 / 6.7 s | $0.123 / $0.127 | BLOCK: Q1, p95, C1 |
| DeepSeek Flash, no thinking | 12.5 / 9.0 pp | 0.9 / 0.4 | 3/3, **0/1** | 1.6 / 1.7 s | $0.004 / $0.004 | BLOCK: Q1, C1 |
| DeepSeek Flash, thinking | 5.9 / 8.9 pp | 0.4 / 0.2 | 3/3, **0/1** | 3.4 / 4.3 s | $0.007 / $0.007 | BLOCK: Q1 |

Keyword engine Q1: 33.2 dev, 30.3 holdout. Q2 risk-label recall is 99.4 pp or more for every reviewer, and
false flags are 0.2 / 0.4 per application for all four. Gate reports: `runs/gate/*_vs_haiku.md`.

**Haiku stays the incumbent.** The gate blocks every challenger at stage 2, and Q1 blocks all three:

- **One pattern decides Q1.** A $40k loan hides among small Intuit payouts (b10). Haiku takes it out of revenue at
  once and sends it to a person; the three challengers call it a payout. That is why every Q1 interval starts at 0 (thinking: [0, +22] pp).
- **Sonnet** is also slower (+3.9 s at p95) and dearer (+56% C1), and its right fix of a casino customer
  came at 0.85, under the 0.90 bar.
- **DeepSeek without thinking** is the fastest and cheapest model, but it is under-confident: right fixes
  (a casino customer, a supplier named "Levy", an invoice wire) came at 0.75 to 0.85 and went to the queue.
  The larger queue costs underwriter time, so C1 is +26% although the model is half the price of Haiku.
- **Thinking fixes that.** The same right fixes reach 0.90 and apply, the queue halves (0.4 per
  application), and C1 is −42%. It costs 3.5x the output tokens of no thinking, and it is still cheaper and
  faster than Haiku here. The latency is not a fair comparison: Haiku's figure includes the CLI, DeepSeek's
  is the HTTP call.
- **On the holdout, all three challengers followed the injection.** Each one saw the instruction text and
  still called a personal loan repayment a sale. The code tripwire sent it to a person, and the final label
  stayed right. The defence does not rely on the model for this reason. Stage 3 did not run, because stage 2
  had already blocked; it would have failed H2.

DeepSeek with thinking is the challenger to retest. Its Q1 gap is one pattern, so the next step is a dev set
with more loans hidden among processor payouts, not a lower bar. Total spend, every iteration included:
**USD 2.15** at list price. Claude: Haiku $0.12 and Sonnet $1.87, paid by subscription. DeepSeek: $0.06
without thinking and $0.11 with it, at the peak-hour price. Each reviewer made 288 or 289 calls.

**What did not work.** (1) The bigger model, and the cheap model without thinking, above. (2) My first policy kept offer-lowering doubts at the
keyword label while they waited; on dev that left $64k of over-offer in the queue. (3) It also queued
changes to a debit's business flag, which no feature reads (2 false flags). I fixed (2) and (3) on dev.

## 4. Results (measured, Haiku)

| | dev | holdout |
|---|---:|---:|
| wrong labels: keyword → reviewed | 239 ($430k) → 13 ($42k) | 169 ($173k) → 39 ($45k) |
| over-offer against true labels: keyword → reviewed | $131,045 → $0 | $62,963 → $14,727 |
| under-offer: keyword → reviewed | $0 → $0 | $0 → $75 |
| hard negatives changed to a wrong label | 0 of 182 | 0 of 91 |
| H1 PII leaks, H4 wrong offer-raising auto-changes | 0, 0 | 0, 0 |

BO1 asked for 50% less over-offer: **−77% on the holdout**, the number to believe. The dev-to-holdout gap is
almost all **one case**: an $18k loan paid under the same text as daily ClassPay payouts (h05). Code split
it into its own pattern, as designed, and every reviewer called it a payout. Haiku caught the same kind of case
on dev (b10). The fix to test next is a code rule (a credit far above its template median that stays
revenue goes to a person). I did not add it, because that is tuning on the holdout; it needs a new one.
Other residuals (`runs/*/*/errors.md`): an employee's child-support remittance kept as a garnishment of the
business, and three Venmo customers queued at 0.85.

**Ground truth I would now label differently, and did not change.** I labelled INTUIT PYMT SOLN (dev) and
CLASSPAY PAYOUT (holdout) `none`. The models say `revenue_verification`, probably rightly. Both are revenue,
so Q1, Q2 and offers do not move, but 10 dev and 31 holdout "wrong labels" are this disagreement. Changing
truth after seeing outputs is how a benchmark flatters its author, so I left it.

## 5. Part 2: credit impact

Each `runs/*/*/report.md` has, per business and for keyword, reviewed and true labels: revenue share of
deposits, NSF and overdraft counts, high-risk share of debits, funder $ per business day, and the offer from
the brief's rule, unchanged. The keyword labels over-offer 8 of 10 dev businesses; with Haiku's labels every
dev offer equals the true one.

**Sensitivity** (`runs/sensitivity.md`; true dev labels, one error type flipped at 2/5/10%, 200 trials):

| error type | offer change per mislabelled txn | at 5%: mean \|Δ offer\|, decisions flipped |
|---|---:|---|
| false revenue (non-revenue credit counted) | +$3,669 to +$4,371 | $813, 0.6% |
| missed revenue | −$480 | $1,598, 0% |
| false active advance | −$340 | $1,448, 0% |
| missed active advance (one payment) | +$112 | $122, 0% |
| false NSF | −$275 to −$2,884 | $8,137, **20.4%** |
| missed NSF | +$2,695 to +$7,188 | $352, 0.9% |
| false or missed high-risk | $0 (the rule ignores it) | the feature moves about 4.6 pp |

Three errors matter: **false revenue on large one-off credits** (rare, thousands each), **NSF near the cliff**
(one count flips "> 5"; 5% false NSFs change 20% of decisions), and **systematic misses** (one missed advance
payment is $112, but one bad keyword hides a whole funder: 57 payments in b02, which random rates
understate). Swaps between excluded groups, random small missed deposits and high-risk labels do not move
the offer.

**False revenue against false active advance.** With 90 days, a credit of $X counted as revenue moves the
offer by 1.2·X/3 = **+0.40·X**; a debit of $Y counted as an advance payment moves it by −20·Y/64 business
days = **−0.31·Y**. Similar per dollar, opposite in risk. False revenue makes the business look **safer**:
Fundo advances more than the cash flow repays and loses principal on default. A false advance makes it look
**riskier**: the deal shrinks or is declined and Fundo loses margin (*estimate*: 20 to 40% of the amount at
factor rates of 1.2 to 1.4, against up to 100% of principal). The dangerous mirror is a *missed* advance,
which hides stacking. This asymmetry sets the 0.90 and 0.70 bars.

**A bank with no NSF fees.** The feature counts fee lines, not bounced payments, so it is zero by
construction, and the risk model treats the applicant like its cleanest borrowers. Mixed in training, it also
learns that NSF counts predict less than they do, for everyone. b05 bounced 7 payments: keyword labels show 0
NSFs and a $40,493 offer, true labels 7 and $0. The reviewer found all 7 from the R01 returns (and h03's 4 R09
returns) without being told about the bank. I would count NSF *events* (fees plus ACH returns R01/R09, as a
code rule now), keep a per-bank "charges NSF fees" table, send a missing value with a flag instead of a false
0, and add a fee-independent signal: days with a negative balance.

**61 days instead of 90.** Sums and counts shrink by a third. Revenue divided by "3 months" is a third low:
b10 has $23,289 a month over 61 observed days, but $15,785 divided by 3, and an offer of $18,941 instead of
$27,946. "> 5 NSFs" gets easier to pass. A short history is also information (a new account, or a bank
switch that leaves NSFs or a funder behind). This code takes history from the first and last dates,
normalizes revenue by observed days and leaves counts unscaled. To detect it: store history days with the
features, alert under 90 days or on gaps, compare its distribution with training, and under a floor ask for
more statements or send the file to a person. `review.py` warns.

## 6. Part 3: production

**Shadow, then a gate.** The reviewer runs on every application after the keyword engine. Its output is
stored, not used: suggestion, confidence, and the offer with and without it. Underwriters label a sample
stratified by offer impact, with every offer-raising suggestion in it. Any prompt, model or policy change
passes `gate.py` in CI (EVAL.md): hard rules, non-inferiority on the labelled set, and superiority on a
holdout before a model or strategy is promoted. CI runs the base branch's gate on the change's outputs, so a
change cannot loosen its own rules; a change to the gate, the metrics or the labelled set needs a person. A **transition** (for example `none → active_advance` on
debits) may change live decisions when its precision on 200 or more labelled cases has a 95% lower bound of
95%, or 99% if it raises offers. Offer-lowering transitions go first; offer-raising ones may stay
suggestions. Flagged text never auto-applies. On an outage, keyword labels go forward as `unreviewed`.

**Silent drift after a retrain.** Each run stores a manifest: input hashes, keyword-list, prompt and schema
hashes, policy, model alias, and **the model the provider says it served**. (1) The frozen labelled set,
with hard negatives and injections, runs in CI on every change and nightly, because a hosted model can change
under its alias. (2) Before a release, recent applications run on old and new versions, and the diff covers
features and decisions, not only labels. (3) In production, each risk-model input (revenue share, NSF count,
funder $/day, label mix, history days) is compared daily per version with a reference window; alert when
the population stability index passes 0.2.

**Reproducing a decline after a keyword fix.** Yes, with these stored immutably: the raw Plaid response
(hashed), keyword-list, prompt and schema versions, model id and served version, **the raw model replies**
(this repository's cache), policy thresholds, underwriter overrides, the feature vector, and the risk-model
and offer-rule versions. A replay runs the stored versions on the stored replies with no model call; here
that is `python3 run.py --offline`, which CI checks is byte-identical. The new version on the same inputs
then shows what changed and whether the decision would, as an adverse-action review needs.

**Underwriters in the loop.** They review patterns, with the reason and the offer impact; on the holdout 36
transactions are 4 decisions. Accept, reject and edit are stored and flow back three ways: repeated
corrections become **keyword fixes** that an engineer reviews (cheaper and more stable than a model call);
corrected cases join the **labelled set** that the gate tests; and the labels feed **per-transition
precision**. A counterparty decision ("SEMINOLE HARD ROCK is b04's customer") carries to that business's
next application. Fine-tuning comes last, if ever.

## 7. Skipped, and why

- **Plaid Sandbox**: its users lack the funder cases, which I had to write anyway.
- **Calibration**: it needs labelled production data.
- **A truly hidden holdout**: I wrote it before the prompt, so I knew its cases; the protection is that no
  change used its results. In production the holdout belongs to people who do not write prompts.
- **Risk model, balances, pending transactions, pagination**: none changes the reviewer question.
- **Unit tests**: the full run against ground truth is the end-to-end test; CI regenerates its committed
  output byte for byte (CI on Python 3.12; I also checked 3.9 and 3.14).

**Known weaknesses.** One answer covers a whole pattern. The tripwire regex is easy to evade, and I wrote
both it and the four test injections. If neither the tripwire nor the model notices an injection and the
model accepts it at 0.90 or more, a change in the business's favour does apply; what limits it then is that
the model cannot set revenue, one call sees one pattern, and the shadow gate measures offer-raising
precision at 99%. H4 reuses the reviewer's `raises_offer`, so it is not an independent check. The gate pairs
runs by pattern, so it cannot compare a keyword or data change (the patterns change); that needs a
transaction-level comparison I did not build. The 120 s per-application fallback in EVAL.md is production
design; the code has only a 180 s timeout per call. Holidays count as business days. Synthetic text is cleaner than real bank text: these numbers
test the mechanism, and real quality needs a labelled sample of real applications.
