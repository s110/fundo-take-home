# Labels still wrong after review (generated)

| pattern | n | $ | keyword label | action | model suggestion (confidence) | model reason |
|---|---:|---:|---|---|---|---|
| `h05|credit|ACH CREDIT CLASSPAY PAYOUT #|none|True` | 31 | $19,520 | none | apply | revenue_verification (0.7) | ClassPay PAYOUT looks like a payment-platform payout of sales, with varying amounts on business days; not a fixed advance repayment. |
| `h05|credit|ACH CREDIT CLASSPAY PAYOUT # [large amount]|none|True` | 1 | $18,000 | none | apply | revenue_verification (0.7) | ClassPay looks like a payment platform. Near-daily payouts of varying amounts match processor settlements. The 18,000 amount is an outlier. |
| `h05|credit|TRANSFER FROM ANGELA BROOKS PERSONAL SAV #|internal_transfer|True` | 1 | $6,000 | internal_transfer | apply | not_avg_revenue (0.8) | Transfer from owner's personal savings, not linked business account; owner injecting personal funds, not sales revenue. |
| `h02|debit|CHILD SUPPORT GARNISHMENT REMIT EMPLOYEE ID #|hr_garnishment|True` | 3 | $1,140 | hr_garnishment | keep | hr_garnishment (0.8) | Monthly child support garnishment remittance for an employee, paid by the business as employer withholding; court-ordered withholding. |
