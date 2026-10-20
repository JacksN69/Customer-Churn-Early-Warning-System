# Parquet migration regression against loaded Power BI

**PASS** — comparison of original 44 behavior/target
fields on all customer-month keys against the saved Power BI DAX export.
The seven additional fields were separately checked in
`reports/parquet_powerbi_additional_fields.md`.

| Metric | Value |
|---|---:|
| Loaded Power BI rows | 569,706 |
| Parquet rows | 569,706 |
| Power BI keys missing in Parquet | 0 |
| Parquet keys missing in Power BI | 0 |
| Duplicate Parquet keys | 0 |
| Fields compared | 44 |
| Fields with discrepancies | 0 |

| Field | Mismatched rows | Result |
|---|---:|---|
| TransactionCount | 0 | PASS |
| TotalAmount | 0 | PASS |
| TransferCount | 0 | PASS |
| PaymentCount | 0 | PASS |
| WithdrawalCount | 0 | PASS |
| DepositCount | 0 | PASS |
| TransferAmount | 0 | PASS |
| PaymentAmount | 0 | PASS |
| WithdrawalAmount | 0 | PASS |
| DepositAmount | 0 | PASS |
| FirstTransactionDate | 0 | PASS |
| LastTransactionDate | 0 | PASS |
| ActiveDays | 0 | PASS |
| WeekendTransactionCount | 0 | PASS |
| TransactionsPerCalendarDay | 0 | PASS |
| WeekendTransactionRatio | 0 | PASS |
| ObservedTenureMonths | 0 | PASS |
| PreferredTransactionType | 0 | PASS |
| PaymentShare | 0 | PASS |
| TransferShare | 0 | PASS |
| WithdrawalShare | 0 | PASS |
| DepositShare | 0 | PASS |
| InactiveMonth | 0 | PASS |
| PreviousTransactionCount | 0 | PASS |
| PreviousTotalAmount | 0 | PASS |
| TransactionCountChange | 0 | PASS |
| TransactionCountChangePct | 0 | PASS |
| TotalAmountChange | 0 | PASS |
| TotalAmountChangePct | 0 | PASS |
| ActivityDeclineFlag | 0 | PASS |
| ConsecutiveInactiveMonths | 0 | PASS |
| DaysSinceLastTransaction | 0 | PASS |
| TransactionCount_Recent3M | 0 | PASS |
| TransactionCount_Previous3M | 0 | PASS |
| TransactionCount_3M_ChangePct | 0 | PASS |
| TotalAmount_Recent3M | 0 | PASS |
| TotalAmount_Previous3M | 0 | PASS |
| TotalAmount_3M_ChangePct | 0 | PASS |
| TransactionDecline50Pct | 0 | PASS |
| SpendingDecline50Pct | 0 | PASS |
| InactiveNextMonth | 0 | PASS |
| ExtendedInactivityNext3Months | 0 | PASS |
| Has6MonthHistory | 0 | PASS |
| EligibleForTraining | 0 | PASS |

All comparisons are null-sensitive; amounts tolerate 0.01 and ratios 1e-8,
with exact comparison for other fields.
