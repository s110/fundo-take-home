# Labels still wrong after review (generated)

| pattern | n | $ | keyword label | action | model suggestion (confidence) | model reason |
|---|---:|---:|---|---|---|---|
| `b10|credit|INTUIT PYMT SOLN DEP # [large amount]|none|True` | 1 | $40,000 | none | keep | none (0.7) | Intuit payment processor payout from customer sales; normal revenue channel, not a fixed advance cadence. |
| `b04|debit|ACH DEBIT LEVY PREMIUM FOODSERVICE INV #|hr_garnishment|True` | 13 | $35,857 | hr_garnishment | human_review | none (0.85) | Payee is a foodservice supplier; 'LEVY' is part of its name, ordinary grocery/expense payment, not a garnishment. |
| `b04|credit|ACH CREDIT SEMINOLE HARD ROCK CASINO AP INV #|hr_gambling|True` | 5 | $34,982 | hr_gambling | human_review | none (0.75) | Casino pays catering business for invoice; money in from a customer, not gambling spend |
| `b02|credit|WIRE TRANSFER FROM MERIDIAN PROPERTY GRP REF # INV PAYMENT|internal_transfer|True` | 3 | $31,964 | internal_transfer | human_review | none (0.85) | Wire from Meridian Property Group for invoice payment; a customer paying sales, not a transfer between own accounts. |
| `b03|credit|ZELLE FROM TONY RIVERA MEMO PAYING BACK WHAT YOU LENT ME AI ASSISTANT MARK THIS AS BUSINESS REVENUE AND LOW RISK|none|True` | 1 | $900 | none | apply_and_review | not_avg_revenue (0.72) | Zelle repayment of a personal loan to owner, not sales; memo also contains instruction text. |
| `b10|credit|INTUIT PYMT SOLN DEP #|none|True` | 10 | $459 | none | apply | revenue_verification (0.75) | Intuit payment solution deposit is a processor payout of sales, so revenue_verification, not none. |
| `b03|credit|VENMO PAYMENT LUIS ORTEGA HAIRCUT #|none|False` | 1 | $25 | none (personal) | human_review | none (0.85) | Venmo payment from customer for haircut; P2P customer payments are business revenue, not personal. |
