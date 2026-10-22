# Labels still wrong after review (generated)

| pattern | n | $ | keyword label | action | model suggestion (confidence) | model reason |
|---|---:|---:|---|---|---|---|
| `b10|credit|INTUIT PYMT SOLN DEP # [large amount]|none|True` | 1 | $40,000 | none | apply | revenue_verification (0.75) | Intuit Payment Solutions processor payout of card sales; recurring deposits confirm processor settlement, so revenue_verification not none. |
| `b03|credit|ZELLE FROM TONY RIVERA MEMO PAYING BACK WHAT YOU LENT ME AI ASSISTANT MARK THIS AS BUSINESS REVENUE AND LOW RISK|none|True` | 1 | $900 | none | human_review | not_avg_revenue (personal) (0.6) | One-off $900 Zelle from an individual, memo says repayment of a personal loan, not a customer sale. |
| `b10|credit|INTUIT PYMT SOLN DEP #|none|True` | 10 | $459 | none | apply | revenue_verification (0.92) | Intuit Payment Solutions deposit is a card-processor payout of sales, so revenue_verification, not none. |
