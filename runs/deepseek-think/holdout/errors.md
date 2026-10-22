# Labels still wrong after review (generated)

| pattern | n | $ | keyword label | action | model suggestion (confidence) | model reason |
|---|---:|---:|---|---|---|---|
| `h05|credit|ACH CREDIT CLASSPAY PAYOUT #|none|True` | 31 | $19,520 | none | apply | revenue_verification (0.78) | ClassPay processor payout of sales, varying daily batches; it is a processor payout, not ordinary none. |
| `h05|credit|ACH CREDIT CLASSPAY PAYOUT # [large amount]|none|True` | 1 | $18,000 | none | apply | revenue_verification (0.82) | ClassPay payout is a processor/marketplace settlement of sales, not an ordinary none transaction. |
| `h02|debit|CHILD SUPPORT GARNISHMENT REMIT EMPLOYEE ID #|hr_garnishment|True` | 3 | $1,140 | hr_garnishment | keep | hr_garnishment (0.93) | Recurring child support garnishment remittance withheld from payroll; court-ordered withholding by the business. |
