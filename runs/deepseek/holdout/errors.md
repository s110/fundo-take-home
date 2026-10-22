# Labels still wrong after review (generated)

| pattern | n | $ | keyword label | action | model suggestion (confidence) | model reason |
|---|---:|---:|---|---|---|---|
| `h01|credit|PAYPAL WORKING CAPITAL LOAN #|revenue_verification|True` | 1 | $22,000 | revenue_verification | apply | not_avg_revenue (0.9) | PayPal Working Capital loan proceeds, not sales payout; loan money in is not revenue. |
| `h05|credit|ACH CREDIT CLASSPAY PAYOUT #|none|True` | 31 | $19,520 | none | apply | revenue_verification (0.85) | ClassPay payout is a card processor sales payout; recurring processor settlement, not ordinary transaction. |
| `h05|credit|ACH CREDIT CLASSPAY PAYOUT # [large amount]|none|True` | 1 | $18,000 | none | apply | revenue_verification (0.9) | ClassPass payout from card processor/marketplace; daily payouts are processor sales settlement, not ordinary deposit. |
| `h02|debit|CHILD SUPPORT GARNISHMENT REMIT EMPLOYEE ID #|hr_garnishment|True` | 3 | $1,140 | hr_garnishment | keep | hr_garnishment (0.95) | Child support garnishment remittance, recurring monthly fixed amount; court-ordered withholding by business. |
| `h03|credit|VENMO FROM TASHA GREEN GEL SET #|none|False` | 5 | $424 | none (personal) | human_review | none (0.82) | Venmo payment from a customer for gel set service; business sales, not owner's personal money |
