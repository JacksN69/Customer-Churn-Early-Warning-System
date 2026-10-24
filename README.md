# Customer Churn Early-Warning System

COFINFAD portfolio project: flag customers who are **active in month T** but may have **zero transactions in month T+1**. The target is *next-month transactional inactivity*, **not** confirmed account closure.

## Problem
Retention teams can contact only a fraction of customers each month. The system ranks active customers by the probability of a skipped month so outreach goes to the highest-risk (and highest-value) ones first.

## Dataset
| Source | Content |
|---|---|
| `data/raw/transactions_data.csv` | 3,159,157 transactions, 48,723 customers, 2023-01-04 to 2023-12-29, types Transfer / Payment / Withdrawal / Deposit (amounts in COP) |
| `data/raw/customer_data.csv` | one undated profile snapshot per customer (54 columns, includes vendor `churn_probability`) |

Raw data quality: [`reports/data_quality_raw.md`](reports/data_quality_raw.md). There is no transaction ID, so 102 exactly identical rows are **kept** (they may be legitimate).

## Architecture
```
data/raw/*.csv
   -> scripts/audit_raw.py                   reports/data_quality_raw.md
   -> src/features/*.sql (DuckDB)            data/processed/{customer_monthly,churn_features,dim_customer}.parquet
   -> src/features/validate_features.py      reports/feature_validation.md
   -> src/features/build_features.py         data/processed/ml_dataset.parquet
   -> src/models/{train_baseline,train_lightgbm,evaluate,predict}.py
   -> src/explainability/shap_explanations.py
   -> outputs/{churn_predictions.parquet, shap_explanations.parquet, model_metrics.json, feature_importance.csv}
   -> Power BI (powerbi/*.pbix): DimCustomer, DimDate, ChurnFeatures, CustomerMonthly (+ ChurnPredictions, pending)
```
Folders: `src/` (pipeline code), `tests/` (pytest), `notebooks/` (EDA), `docs/` (registry, decisions, status), `powerquery/` (M queries; heavy M logic archived in `legacy/`), `reports/` (generated Markdown), `models/` and `outputs/` (git-ignored artifacts).

## Data preparation
- One row = one customer x one calendar month, from the customer's first transaction month to Dec 2023. **Zero-activity months are explicit rows** (101,985 of 569,706).
- Reconciliation: `SUM(TransactionCount)` equals the 3,159,157 raw rows and amounts match exactly; type counts/amounts sum to the totals; shares sum to 100% for active months; `WeekendTransactionCount <= TransactionCount`; `ActiveDays >= 1` iff active ([`reports/feature_validation.md`](reports/feature_validation.md)).
- Rolling 3M features and targets are re-derived independently (self-joins, no window functions) for a seeded customer sample and match with 0 mismatches.
- Power Query originally computed these tables; the logic was ported to DuckDB/Parquet only after the outputs were proven identical to Power BI (`reports/parquet_powerbi_full_parity.md`).

## Churn definition
`InactiveNextMonth = 1` if `TransactionCount(T) > 0` and `TransactionCount(T+1) = 0`; `0` if activity continues; `NULL` if T+1 is unavailable or T is inactive.
**Churn is operationalized as next-month transactional inactivity because confirmed account-closure labels are not available.** `ExtendedInactivityNext3Months` (three silent months) is descriptive only. The vendor `churn_probability` is never a feature or a label.

## Feature engineering
- Base features from `ChurnFeatures` (counts, amounts, shares, 3M windows, recency, declines), approved row by row in [`docs/FEATURE_REGISTRY.csv`](docs/FEATURE_REGISTRY.csv).
- Added in Python (`src/features/build_features.py`), each tied to a behavioural hypothesis: 3M/6M average activity and spend, active months in 3M/6M, 3M volatility, transaction-type diversity, Recent3M type shares, and null indicators for undefined percentage changes. 61 features in total.
- Constant features are detected automatically (`nunique <= 1`) and removed.

## Leakage prevention
- Every feature uses data up to the end of month T; window frames end at `CURRENT ROW` (checked by `tests/test_leakage.py`).
- Customer profile snapshots (age, satisfaction, CLV, products, ...) are **not** model inputs: they are undated, so availability at T cannot be proven. A clearly labelled `behavior+static_profile` experiment is trained for comparison only.
- `ObservedTenureMonths` is excluded: ~80% of customers start in Jan 2023, so it equals the calendar-month index and test/scoring months fall outside the training range.
- Splits are chronological, never shuffled. Thresholds and risk tiers are learned on the validation month only.

## EDA
[`notebooks/01_eda.ipynb`](notebooks/01_eda.ipynb) and [`reports/eda_summary.md`](reports/eda_summary.md). Key results: target rate 17.4% (14.8% to 18.9% by month); ~73% of "inactive next month" rows are active again at T+2 (transient gaps); inactive-next customers are chronically low-activity (~1.4 vs ~7.8 transactions/month) with no visible decline beforehand; recency is monotone (8.2% to 24.9%); profile attributes give almost no segmentation signal.

## Modeling
Chronological design: train Jun-Sep 2023 (146,093 rows), validation Oct (39,389), test Nov (38,878); production refit Jun-Nov; December scored for January 2024 (38,531 customers, outcome unobserved).
Candidates: Logistic Regression (unweighted and `class_weight="balanced"`), LightGBM (three configurations, early stopping on validation log-loss), plus the profile experiment. Selection: highest validation PR-AUC. Experiments are logged locally to `reports/model_experiments.csv` (git-ignored). Public summary results are in [`reports/model_evaluation.md`](reports/model_evaluation.md).

## Evaluation
November test month (evaluated once), selected model `lightgbm_leaves31`: ROC-AUC 0.740, PR-AUC 0.324 (prevalence 18.9%), Precision@Top10% 33.7% and Recall@Top10% 17.9% (lift 1.8x), Precision@Top5% 34.6%, expected calibration error 0.015. Full tables (confusion matrices at the capacity, F1 and cost thresholds, risk tiers, calibration deciles) are in [`reports/model_evaluation.md`](reports/model_evaluation.md) and `outputs/model_metrics.json`.
The operating threshold is capacity-based (top 10% of active customers). Risk tiers (Critical / High / Medium / Low) use cumulative capacity cutoffs from validation. **Caveat:** Critical, High and Medium have practically the same observed rate (~33-35% vs 12.8% for Low), so the model separates an elevated group from the rest rather than four distinct levels.

## Explainability
SHAP (`outputs/shap_explanations.parquet`, `outputs/feature_importance.csv`) provides TopDriver1-3 with impact and value per scored customer-month. These are **model drivers, not causes of churn**. `AvgTransactionCount_6M` dominates, followed by Previous/Recent 3M transaction counts.

## Power BI dashboard
The repository contains an exported semantic model (`powerbi/model.bim`), DAX measures, and scripts that define six German-language Power BI pages. The exported model includes `ChurnPredictions`; its underlying Parquet file is produced locally. The `.pbix` binary is deliberately not published, so page rendering, dataset refresh, and the saved report must be checked in Power BI Desktop before the dashboard can be treated as delivered.

## Business implications
Prioritise outreach using probability x Recent3M value (`PriorityScore`, `PriorityQuadrant` in the predictions). Because most gaps are transient and low-frequency customers drive the signal, treat the score as *inactivity risk*; do not describe customers as lost.

## Limitations
- No confirmed account-closure label; the target is transactional inactivity (and ~73% of those rows return by T+2).
- Only 12 months of data (2023); left-censored customer history.
- Customer snapshot fields have uncertain observation timing and are excluded from the model.
- January 2024 outcomes are unobserved, so December scores are unverified.
- Tier cutoffs from validation drift slightly on the refit December model (6.5% / 6.1% / 19.5% / 67.8% instead of 5 / 5 / 20 / 70).
- SHAP relationships are explanatory, not causal. The data look synthetic or banded (for example, only six distinct ages).

## How to reproduce
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m src.pipeline.run_pipeline              # raw audit -> ETL -> validation -> dataset -> models -> SHAP
.\.venv\Scripts\python.exe -m src.pipeline.run_pipeline --skip-etl   # keep existing Parquet (e.g. while Power BI has it open)
.\.venv\Scripts\python.exe -m pytest tests                           # unit + data tests
.\.venv\Scripts\python.exe notebooks\build_eda_notebook.py           # re-execute the EDA notebook
```
Inputs live in `data/raw/` and are never modified. Raw and processed data, PBIX binaries, and model/prediction artifacts are git-ignored because they may include customer-level records. A fresh public checkout cannot reproduce the published metrics until the source datasets are supplied locally. For the Power BI build, use the report-generation scripts and adjust local paths as documented in [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md).
The earlier exploratory scripts under `scripts/` (`train_baseline.py`, `model_diagnostics.py`, ...) are superseded by `src/` and kept for history.
