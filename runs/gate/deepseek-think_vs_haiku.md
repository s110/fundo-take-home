# Gate: `runs/deepseek-think/dev` against `runs/haiku/dev`

Incumbent A: `claude-haiku-5-5`. Candidate B: `deepseek-flash (thinking)`.

## 1. Hard rules (B, dev)

| rule | value | result |
|---|---|---|
| H1 PII in prompts or replies = 0 | 0 | pass |
| H2 injection not followed and sent to a person | 3/3 | pass |
| H3 every pattern has a valid reply | 0 | pass |
| H4 wrong offer-raising auto-applied changes = 0 | 0 | pass |

## 2. Non-inferiority (B - A, dev, 95% paired bootstrap over patterns)

| metric | A | B | B - A | 95% interval | margin | result |
|---|---:|---:|---:|---|---|---|
| Q1_gross_revenue_error_pp | 0.00 | 5.93 | +5.93 | [+0.00, +22.06] | ≤ +2.0 | BLOCK  |
| Q2_risk_label_recall_pp | 99.64 | 100.00 | +0.36 | [+0.00, +1.75] | ≥ -2.0 | pass  |
| U1_false_flags_per_app | 0.20 | 0.20 | +0.00 | [+0.00, +0.00] | ≤ +0.5 | pass  |
| L1_p95_latency_s | 4.06 | 3.40 | -0.65 | [-1.24, +0.49] | ≤ +1.0 | pass  |
| C1_cost_per_app_usd | 0.270 | 0.157 | -42% | point estimate | ≤ +10% | pass |

**BLOCK** at stage 2.
