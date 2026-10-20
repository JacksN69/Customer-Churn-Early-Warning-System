# Next-month transactional inactivity: EDA + chronological baseline

**Target:** among customers with activity in month T, zero transactions in T+1,
not confirmed account closure. Training starts after six observed months.
Raw transaction dates determine all predictor values; **no customer snapshot fields**,
`churn_probability`, customer IDs, dates or future labels are model inputs.

## Chronological design
- Training: customer-months June–September 2023 (146,093 rows).
- Model selection: October 2023 (39,389 rows).
- Final refit for the selected model: June–October 2023 (185,482 rows).
- One-time holdout: November 2023 (38,878 rows), predicting December.
- Production-style score: December 2023 (38,531 active customers),
  predicting January 2024 (**no observed January outcomes**).
- Same customers can appear in different months, matching a repeat-scoring use case.
- Feature imputation for Logistic Regression learns medians **on the training fold
  only**, with missingness indicator columns. HistGradientBoosting handles NaN
  natively; raw missing fields are never overwritten with zero.

## Inactivity label prevalence
| Month T | Eligible rows | Positive rows | Inactivity rate |
|---|---:|---:|---:|
| 2023-01 | 0 | 0 | N/A |
| 2023-02 | 0 | 0 | N/A |
| 2023-03 | 0 | 0 | N/A |
| 2023-04 | 0 | 0 | N/A |
| 2023-05 | 0 | 0 | N/A |
| 2023-06 | 31,362 | 4,649 | 14.82% |
| 2023-07 | 37,114 | 6,196 | 16.69% |
| 2023-08 | 38,795 | 6,971 | 17.97% |
| 2023-09 | 38,822 | 6,698 | 17.25% |
| 2023-10 | 39,389 | 7,193 | 18.26% |
| 2023-11 | 38,878 | 7,332 | 18.86% |
| 2023-12 | 0 | 0 | N/A |

## Validation model comparison (October)
| Model | N | Actual rate | ROC AUC | PR AUC | Precision @ 10% | Recall @ 10% | Brier |
|---|---:|---:|---:|---:|---:|---:|---:|
| constant_prevalence | 39,389 | 18.3% | 0.5000 | 0.1826 | 17.4% | 9.5% | 0.1495 |
| logistic_regression | 39,389 | 18.3% | 0.7235 | 0.2909 | 28.1% | 15.4% | 0.1354 |
| hist_gradient_boosting | 39,389 | 18.3% | 0.7336 | 0.3052 | 32.0% | 17.5% | 0.1337 |

Note: constant-prevalence ranking is uninformative because all its scores are tied; constant-baseline top-K entries reflect arbitrary tie order, not a deployable selection rule.

Selected model (highest validation PR AUC): **hist_gradient_boosting**

## November holdout (one-time evaluation)
| Metric | Selected model | Constant-rate baseline |
|---|---:|---:|
| Observations | 38,878 | 38,878 |
| Observed positive rate | 18.86% | 18.86% |
| ROC AUC | 0.7393 | 0.5000 |
| PR AUC | 0.3224 | 0.1886 |
| Brier loss (lower better) | 0.1362 | 0.1533 |
| Precision @ top 5% | 33.49% | 18.83% |
| Recall @ top 5% | 8.88% | 4.99% |
| Precision @ top 10% | 33.02% | 18.54% |
| Recall @ top 10% | 17.51% | 9.83% |

## December scoring
- Scored active customers: 38,531.
- Mean risk score: 17.875%; range 0.009%–50.512%.
- Flagged top 10% for hypothetical outreach: 3,854.
- Private Parquet: `data/processed/december_risk_scores.parquet`.
- No outreach, customer contact, or message was sent.
- Scores are **experimental**; evaluate calibration and segment stability before
  operational deployment. Risk is predictive association, not causal explanation.

## Missing transaction-derived features in June–September train
| Feature | Training NULL |
|---|---:|
| TransactionCountChangePct | 16.72% |
| TotalAmountChangePct | 16.72% |
| TransactionCount_3M_ChangePct | 0.98% |
| TotalAmount_3M_ChangePct | 0.98% |

## Artifacts and caution
- Saved scikit-learn estimator: `models/churn_early_warning.joblib`, local private.
- Predictors (45): TransactionCount, TotalAmount, AverageAmount, MaxAmount, TransferCount, PaymentCount, WithdrawalCount, DepositCount, TransferAmount, PaymentAmount, WithdrawalAmount, DepositAmount, ActiveDays, WeekendTransactionCount, TransactionsPerCalendarDay, WeekendTransactionRatio, ObservedTenureMonths, PaymentShare, TransferShare, WithdrawalShare, DepositShare, PreviousTransactionCount, PreviousTotalAmount, PreviousPaymentCount, PreviousWithdrawalCount, PreviousDepositCount, PreviousTransferCount, TransactionCountChange, TransactionCountChangePct, TotalAmountChange, TotalAmountChangePct, ActivityDeclineFlag, DaysSinceLastTransaction, TransactionCount_Recent3M, TransactionCount_Previous3M, TransactionCount_3M_ChangePct, TotalAmount_Recent3M, TotalAmount_Previous3M, TotalAmount_3M_ChangePct, TransactionDecline50Pct, SpendingDecline50Pct, PreferredType_Transfer, PreferredType_Payment, PreferredType_Withdrawal, PreferredType_Deposit.
- Full result (numeric values): `reports/model_metrics.json`.
- Model uses all strictly dated transaction-derived predictors and a deterministic
  one-hot of the transaction type category; no raw customer-profile snapshots.
- Dataset is synthetic/portfolio-like unless provenance supports real-world
  operational use; do not advertise evidence of causal churn reduction.
