# Evaluation contract: objectives, SLOs, metrics and the release gate

I wrote this file before the first model run, and I committed it before any result existed. The
thresholds below are not tuned to the results. If I change one later, the change is a separate commit
that gives the reason.

Numbers marked *assumption* are not measured. They are inputs that the business must confirm.

## 1. Business objectives

The reviewer exists to change underwriting outcomes. Each objective names what it protects.

| id | objective | why it matters |
|---|---|---|
| BO1 | Fewer dollars over-advanced. Over-offer (offer minus true offer, summed where positive) must fall by at least 50% against the keyword labels. | False revenue and hidden funders make a business look safer than it is. Fundo then advances more than the cash flow can repay. This is principal at risk. |
| BO2 | Do not shrink good deals. Under-offer must not grow by more than the over-offer falls. | A false risk label declines or shrinks a good deal. Fundo loses margin, not principal, so it costs less per dollar (see SOLUTION.md, Part 2), but it is still a loss. |
| BO3 | Spend little underwriter time. The reviewer sends patterns, not single transactions, to a person, and false flags stay rare. | Underwriter time is the most expensive resource in the loop. A flag that is wrong (a hard negative) is pure waste. |
| BO4 | Every decision can be reproduced. | A declined business can ask why. A keyword fix can change labels later. We must rebuild the original decision from stored inputs, without a model call. |

## 2. Service level objectives (production)

The repository cannot measure these over time. It measures the same quantities on one run, and the
gate below protects them on every change.

| SLO | target | reason for the number |
|---|---|---|
| Review latency | p95 ≤ 120 s per application, from Plaid data to reviewer output | Offers for revenue-based advances go out the same day. Two minutes is small next to the human part of the process. A slow model never blocks a decision: after 120 s the legacy labels go forward, marked `unreviewed`. |
| Review coverage | ≥ 99% of applications have no `unreviewed` pattern, per 28 days | An unreviewed pattern keeps its keyword label, so a miss loses the improvement but does not make a new error. 1% covers provider outages (hosted APIs publish 99.5% to 99.9% monthly uptime) and replies that are invalid twice. |
| Invalid output | ≤ 0.5% of calls invalid after one retry | Above this, coverage cannot hold. In the replay set the target is 0 (hard rule H3). |
| Model cost | ≤ USD 0.05 per application | An underwriter minute costs about USD 0.75 (*assumption*: USD 45 per hour, loaded). The model must cost less than 5 seconds of a person. |
| Underwriter queue | ≤ 2 patterns per application on average, and ≤ 0.5 false flags | At 30 s per pattern (*assumption*), 2 patterns are 1 minute. Manual statement review takes far longer. A false flag above 1 in 2 applications teaches underwriters to ignore flags. |
| Auto-applied precision (shadow) | 95% lower bound ≥ 95% per transition, on ≥ 200 labelled cases; ≥ 99% for changes that raise an offer | See SOLUTION.md, Part 3. A wrong change that raises an offer costs principal (BO1), so its bar is higher. |

## 3. Metrics

All metrics come from `fundo/evaluate.py`. The **pattern** is the unit of decision: transactions of one
business with the same direction, the same description template (digits removed), and the same keyword
label. The model makes one decision per pattern, so every confidence interval resamples patterns.

| id | metric | definition |
|---|---|---|
| Q1 | Gross revenue error (pp) | Dollars on the wrong side of the revenue line, per month, divided by true monthly revenue. Over-counts and under-counts do not cancel. Lower is better. |
| Q2 | Risk-label recall (pp) | Of the transactions whose true group is `active_advance`, `nsf`, `overdraft` or a high-risk group, the share whose final group is correct. Higher is better. |
| U1 | False flags per application | Patterns that the reviewer changed or sent to a person, where the keyword label was correct. |
| U2 | Queue per application | Patterns sent to a person. |
| L1 | p95 latency per pattern (s) | Model time for one pattern, retries included. |
| C1 | Cost per application (USD) | Model cost + U2 × 0.5 min × USD 0.75 (*assumption*). Underwriter time is part of the cost on purpose: a cheap model that floods the queue is not cheap. |
| R1 | Over-offer and under-offer (USD) | Per business, from the offer rule, against the offer on true labels. Reported, not gated: 10 businesses are too few for an interval. |

Scoring rule for a label, fixed now: the group must match. For a credit, the business flag must match
too. For a personal credit, `none` and `not_avg_revenue` count as the same label, because neither is
revenue and no feature tells them apart. The business flag on a debit feeds no feature and is not scored.

## 4. The release gate

`gate.py` compares a candidate run B with the incumbent run A. CI runs it on every pull request.

```
pull request
     │
     ▼
1. Hard rules (on B) ──────────── any failure ──► BLOCK
   H1 PII in prompts or replies = 0
   H2 injection: 100% not followed and sent to a person
   H3 valid reply after ≤ 1 retry: 100%
   H4 wrong offer-raising auto-applied changes = 0
     │ pass
     ▼
2. Non-inferiority (B − A, dev set, 95% paired bootstrap)
   Q1 upper bound ≤ +2.0 pp
   Q2 lower bound ≥ −2.0 pp
   U1 upper bound ≤ +0.5 per application
   L1 upper bound ≤ +1.0 s
   C1 point estimate ≤ +10%
     │ all pass            point estimate beyond margin ──► BLOCK
     │                     only the bound beyond margin ──► INCONCLUSIVE (grow the set)
     ▼
   MERGE
     │  only for a change of model or strategy
     ▼
3. Superiority (holdout set, which no prompt decision used)
   H1-H4 hold on the holdout too
   Q1 upper bound < 0, or Q2 lower bound > 0, and the other one non-inferior
     │ pass
     ▼
   PROMOTE (the candidate becomes the incumbent)
```

### Why these thresholds

- **H1-H4 are zero-tolerance.** One leak of personal data, one followed injection, or one wrong change
  that raises an offer is a defect of a different kind. An average must not hide it.
- **Q1 margin 2.0 pp.** Offers are quoted in round thousands (*assumption*). On the dev set, true
  monthly revenue is about USD 34,000 per business, so 2 pp is about USD 680 a month and USD 820 of offer
  (1.2 ×). That is below one rounding step. A smaller margin needs a set much larger than 10 businesses.
- **Q2 margin 2.0 pp.** The same tolerance as Q1, so that a candidate cannot buy revenue accuracy with
  missed funders or NSFs.
- **U1 margin +0.5 per application.** Half a false flag per application is 15 s of underwriter time
  (*assumption*: 30 s per pattern). It is also the SLO ceiling, so one bad change cannot use all of it.
- **L1 margin +1.0 s per pattern.** An application has about 20 patterns (19 on average in dev) and
  the pipeline runs 4 calls at a time, so the slowest calls add up over about 5 rounds. +1.0 s per call
  is about +5 s per application, 4% of the 120 s SLO. Several changes in a row cannot quietly use the
  whole budget.
- **C1 margin +10%.** The cost includes underwriter time, so the margin catches a candidate that is
  cheaper per call but sends more work to people. A point estimate is enough: cost is not noisy.
- **95% paired bootstrap.** 2,000 resamples of patterns within each business, A and B on the same
  resample, fixed seed. Paired, because A and B see the same patterns; within each business, because
  revenue is normalized per business. The bound used is the 2.5% or 97.5% percentile, a one-sided test
  at 2.5%.
- **Inconclusive is a result.** When the point estimate is inside the margin but the bound is outside,
  the set is too small to decide. The gate prints about how many times larger the set must be, from the
  rule that an interval narrows with the square root of its size.

### Holdout

`data/holdout` has 5 businesses with the same kinds of risk as dev but other counterparties, funders,
banks and spellings (PayPal Working Capital, CAN Capital, R09 returns, CH13 written another way, a
transfer across a month end). The rule for this repository: no prompt, keyword or policy change may use
holdout results. Only stage 3 of the gate reads it. In production it is a sample that the prompt authors
never see. Here it is in the repository, so the rule is a discipline and git history is the audit.

## 5. What this contract does not cover

- Calibration. The confidence bars (0.70 and 0.90) are a risk order, not probabilities. Calibration
  needs labelled production data.
- Real data. Both sets are synthetic and I wrote them. The gate shows the mechanism. Its numbers only
  mean something on a labelled sample of real applications.
