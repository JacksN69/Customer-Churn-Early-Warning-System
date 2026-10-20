# Model evaluation (run 20261016-145800)

**Target:** InactiveNextMonth: next-month transactional inactivity (not confirmed account closure).

**Selected model:** `lightgbm_leaves31` (61 features, version `lightgbm_leaves31-20261016-145800`).
Selection: highest validation PR-AUC among production-eligible candidates (test month untouched).

## Chronological design

- Train 2023-06..2023-09 (146,093 rows), validation 2023-10 (39,389), test 2023-11 (38,878).
- Production refit 2023-06..2023-11; scored 2023-12 (38,531 customers) for 2024-01 (unobserved).

## Validation comparison (October)

| Model | Feature set | ROC-AUC | PR-AUC | P@5% | R@5% | P@10% | R@10% | Eligible |
|---|---|---:|---:|---:|---:|---:|---:|---|
| logistic_regression | behavior | 0.7243 | 0.2907 | 0.282 | 0.077 | 0.282 | 0.154 | yes |
| logistic_regression_balanced | behavior | 0.7252 | 0.2901 | 0.281 | 0.077 | 0.279 | 0.153 | yes |
| lightgbm_leaves31 | behavior | 0.7370 | 0.3123 | 0.332 | 0.091 | 0.329 | 0.180 | yes |
| lightgbm_leaves15 | behavior | 0.7366 | 0.3112 | 0.337 | 0.092 | 0.324 | 0.178 | yes |
| lightgbm_leaves31_pos_weight | behavior | 0.7362 | 0.3081 | 0.317 | 0.087 | 0.331 | 0.181 | yes |
| lightgbm_leaves31_with_profile | behavior+static_profile | 0.7345 | 0.3054 | 0.319 | 0.087 | 0.310 | 0.170 | experiment only |

## Test (November, evaluated once)

Prevalence 18.86% (a constant-score model has PR-AUC = prevalence).

| Metric | Value |
|---|---:|
| ROC-AUC | 0.7405 |
| PR-AUC | 0.3241 |
| Brier | 0.1362 |
| Precision@Top5% / Recall@Top5% | 0.346 / 0.092 (lift 1.83x) |
| Precision@Top10% / Recall@Top10% | 0.337 / 0.179 (lift 1.79x) |
| Expected calibration error | 0.0152 |

## Operating thresholds (learned on validation, applied to test)

| Rule | Threshold | Flagged | Precision | Recall | F1 | TN | FP | FN | TP |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| operating: top 10% of active customers (retention capacity) | 0.3179 | 9.0% | 0.338 | 0.162 | 0.219 | 29,221 | 2,325 | 6,143 | 1,189 |
| f1_optimal: maximises F1 on validation | 0.2079 | 48.3% | 0.308 | 0.788 | 0.443 | 18,546 | 13,000 | 1,554 | 5,778 |
| cost_optimal: minimises 5 x missed + 1 x unneeded contacts on validation (placeholder costs, replace with business values) | 0.1647 | 54.8% | 0.299 | 0.868 | 0.445 | 16,608 | 14,938 | 966 | 6,366 |

**Chosen operating threshold:** the capacity rule (top 10% of active customers), because outreach volume is limited by retention-team capacity. The F1 and cost rules are shown for comparison; the cost rule uses placeholder unit costs.

## Risk tiers (cutoffs from validation)

| Level | Test customers | Test share | Observed inactive rate | Validation observed rate |
|---|---:|---:|---:|---:|
| Critical | 1,716 | 4.4% | 34.6% | 33.2% |
| High | 1,798 | 4.6% | 33.1% | 32.7% |
| Medium | 8,102 | 20.8% | 32.9% | 31.5% |
| Low | 27,262 | 70.1% | 12.8% | 12.4% |

## Calibration by decile (test, highest risk first)

| Decile | Customers | Observed | Mean predicted |
|---|---:|---:|---:|
| 1 | 3,888 | 33.7% | 32.8% |
| 2 | 3,888 | 33.5% | 31.1% |
| 3 | 3,888 | 32.3% | 29.7% |
| 4 | 3,888 | 28.5% | 27.2% |
| 5 | 3,888 | 24.9% | 22.5% |
| 6 | 3,888 | 19.5% | 16.3% |
| 7 | 3,888 | 10.5% | 9.3% |
| 8 | 3,888 | 4.9% | 3.9% |
| 9 | 3,887 | 0.8% | 0.6% |
| 10 | 3,887 | 0.0% | 0.2% |

## December scoring (unverified)

38,531 customers, mean probability 17.75%. Risk shares: Low 67.8%, Medium 19.5%, High 6.1%, Critical 6.5%.

## Limitations

- January 2024 outcomes are unobserved: December scores are unverified prospective scores
- No confirmed account-closure label; target is transactional inactivity
- About 73% of inactive-next-month customer-months are active again at T+2 (transient gaps, see EDA)
- SHAP/permutation results describe the model, not causal drivers

## Warnings

- Critical/High/Medium tiers have practically the same observed inactivity rate on the test month (34.6% / 33.1% / 32.9% vs Low 12.8%). The model separates an elevated-risk group from the rest but not risk levels within it; treat Medium+ as one elevated group and use probability/PriorityScore for ordering inside it
