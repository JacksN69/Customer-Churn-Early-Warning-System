# Additional Power BI versus Parquet field comparison

| Metric | Value |
|---|---:|
| Power BI rows | 569,706 |
| Parquet rows | 569,706 |
| Extra Power BI keys | 0 |
| Missing Power BI keys | 0 |

| Field | Mismatches | Result |
|---|---:|---|
| CustomerStartMonth | 0 | PASS |
| AverageAmount | 0 | PASS |
| MaxAmount | 0 | PASS |
| PreviousPaymentCount | 0 | PASS |
| PreviousWithdrawalCount | 0 | PASS |
| PreviousDepositCount | 0 | PASS |
| PreviousTransferCount | 0 | PASS |

## Verdict
**PASS**
The seven fields were compared on all customer-month keys. AverageAmount
uses an absolute tolerance of 0.01; other data types use exact/null-safe comparison.
