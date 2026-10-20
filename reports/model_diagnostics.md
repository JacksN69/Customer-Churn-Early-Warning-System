# Historical holdout diagnostics (November 2023)

Model: hist_gradient_boosting. Selection and training used months at/before October.
November was a **single held-out test**, not used to fit the model.
Observation unit: active customer in November, zero transactions in December target.

## Reliability by predicted risk decile
Ranked highest to lowest predicted risk. Compare mean predicted risk with observed
frequency; these are portfolio-style checks, **not evidence of production calibration**.

| Risk decile | Customers | Observed inactivity | Mean predicted probability |
|---|---:|---:|---:|
| 1 | 3,888 | 33.0% | 32.9% |
| 2 | 3,888 | 34.0% | 31.1% |
| 3 | 3,888 | 32.1% | 30.2% |
| 4 | 3,888 | 28.3% | 28.5% |
| 5 | 3,888 | 25.7% | 24.1% |
| 6 | 3,888 | 19.2% | 16.9% |
| 7 | 3,888 | 10.6% | 9.8% |
| 8 | 3,888 | 4.7% | 4.0% |
| 9 | 3,887 | 0.8% | 0.6% |
| 10 | 3,887 | 0.0% | 0.0% |

- Expected calibration error (10 equal-population bins): **0.0108**.
- Overall Brier score: 0.1362 (lower is better).
- PR-AUC: 0.3224 (compared with holdout prevalence 0.1886).
- Calibration improvement would require a separate dated calibration period;
  don't tune retrospectively on the final November test.

## Diagnostic feature influence (permutation, November sample)
Importance = decrease in average precision when one column is shuffled,
averaged over 2 repetitions on a seeded 8,000-row sample. Negative values
can arise from variance or correlated features.

| Rank | Feature | AP decrease |
|---|---|---:|
| 1 | TransactionCount_Previous3M | 0.0571 |
| 2 | TransactionCount_Recent3M | 0.0382 |
| 3 | PreviousTransferCount | 0.0044 |
| 4 | PreviousPaymentCount | 0.0029 |
| 5 | DepositAmount | 0.0020 |
| 6 | WithdrawalAmount | 0.0018 |
| 7 | PreviousTransactionCount | 0.0018 |
| 8 | PaymentCount | 0.0013 |
| 9 | PaymentAmount | 0.0010 |
| 10 | WeekendTransactionCount | 0.0010 |
| 11 | WeekendTransactionRatio | 0.0009 |
| 12 | PreviousTotalAmount | 0.0008 |
| 13 | PreviousDepositCount | 0.0008 |
| 14 | WithdrawalShare | 0.0006 |
| 15 | TransactionDecline50Pct | 0.0005 |

**Limitations:** Feature importance is predictive, not causal; correlated
transaction features can substitute for one another. This is diagnostic
after the model was frozen; do not retune the model using test results.

No customer-profile snapshots or demographics are included in this model.
