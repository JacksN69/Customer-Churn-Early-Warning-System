# Power BI ↔ DuckDB customer-month reconciliation

## Method

Direct DAX export from the open saved Power BI Desktop model (`ChurnFeatures`)
was joined by (`customer_id`, `Month`) to an independent DuckDB build from
the unmodified raw CSV. This is a *saved-model* comparison, not a source refresh.
All 44 non-key columns below were evaluated for every matched row.
Amounts tolerate up to 0.01; percentage/rate floats up to 1e-8; other values exact.

| Metric | Value |
|---|---:|
| Power BI rows | 569,706 |
| DuckDB rows | 569,706 |
| Invalid Power BI keys | 0 |
| Duplicate Power BI keys | 0 |
| Unexpected Power BI keys | 0 |
| Missing Power BI keys | 0 |
| Fields with discrepancies | 0 / 44 |

## Per-field comparison

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

## Verdict

**PASS — exact key population and all selected fields reconcile**

Notes:
- This audit compares the existing loaded/saved PBIX model with the raw CSVs.
- It does not prove that a future Power BI refresh will use the same CSV file.
- Snapshot export `reports/powerbi_customer_month_actual.csv` contains
  customer IDs and must not be published to GitHub.
- Unknown point-in-time provenance of customer profile fields is not resolved
  by this behavioral parity audit.
