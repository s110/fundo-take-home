# Labels still wrong after review (generated)

| pattern | n | $ | keyword label | action | model suggestion (confidence) | model reason |
|---|---:|---:|---|---|---|---|
| `h05|credit|ACH CREDIT CLASSPAY PAYOUT #|none|True` | 31 | $19,520 | none | apply_and_review | revenue_verification (0.6) | "CLASSPAY PAYOUT" near-daily with varying amounts looks like a tutoring platform's payout of sales, not a plain customer payment. Revenue status unchanged. |
| `h05|credit|ACH CREDIT CLASSPAY PAYOUT # [large amount]|none|True` | 1 | $18,000 | none | apply_and_review | revenue_verification (0.6) | "CLASSPAY PAYOUT" looks like a platform payout of tutoring sales, not a direct customer ACH. Still revenue; not a fixed advance repayment. |
| `h05|credit|TRANSFER FROM ANGELA BROOKS PERSONAL SAV #|internal_transfer|True` | 1 | $6,000 | internal_transfer | apply | not_avg_revenue (0.8) | Transfer from owner's personal savings, not a business-linked account. Owner personal money in, so not an internal transfer. |
| `h02|debit|CHILD SUPPORT GARNISHMENT REMIT EMPLOYEE ID #|hr_garnishment|True` | 3 | $1,140 | hr_garnishment | keep | hr_garnishment (0.85) | Child support garnishment remittance from business checking, recurring monthly at $380. Matches hr_garnishment; business account. |
| `h03|credit|VENMO FROM JESSICA LEE GEL SET #|none|False` | 3 | $188 | none (personal) | human_review | none (0.85) | Venmo payments from a customer for gel nail service, recurring weekly. Customer payment via P2P app is business revenue. |
