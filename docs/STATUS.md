# Project status — 20 October 2026

The numerical results below are from the locally executed October 16 pipeline. The public checkout does not contain private datasets or the final PBIX binary.

## Done and verified
- Raw audit, 3,159,157 transactions / 48,723 customers (`reports/data_quality_raw.md`).
- CustomerMonthly / ChurnFeatures / DimCustomer built by DuckDB (`src/features/*.sql`) and reconciled to raw data and the original Power BI model; independent recomputation and invariants in `reports/feature_validation.md` (all PASS); pytest suite with hand-computed cases (19 tests).
- ML dataset (`data/processed/ml_dataset.parquet`): 61 features, chronological split Jun–Sep / Oct / Nov, December unlabelled scoring month; constant-feature detection built in (`reports/ml_dataset.md`).
- Models: Logistic Regression (unweighted and balanced) and LightGBM; selected `lightgbm_leaves31`. Test (Nov) ROC-AUC 0.740, PR-AUC 0.324, Precision@Top10% 33.7%, Recall@Top10% 17.9%, ECE 0.015 (`reports/model_evaluation.md`, `outputs/model_metrics.json`).
- SHAP top-3 drivers and global importance (`outputs/shap_explanations.parquet`, `outputs/feature_importance.csv`); predictions with RiskLevel and PriorityScore/PriorityQuadrant in `outputs/churn_predictions.parquet`.
- Experiment log: `reports/model_experiments.csv`.
- One-command pipeline: `python -m src.pipeline.run_pipeline` (verified end to end on 16 Oct 2026).
- Power BI: `DimDate` (monthly) added, relationships `DimDate -> ChurnFeatures[Month]` and `DimDate -> CustomerMonthly[Month]`; `DimCustomer -> ChurnFeatures[customer_id]` verified (single direction). Loaded tables: CustomerMonthly, ChurnFeatures, DimCustomer, DimDate; `transactions_data` and `customer_data` are staging queries with load disabled. Checkpoint before change: `powerbi/backups/*before-dimdate-20261015.pbix`.
- EDA notebook and written summary (`notebooks/01_eda.ipynb`, `reports/eda_summary.md`).

## Findings that change the narrative
- ~73% of inactive-next-month rows are active again at T+2: the target is mostly a skipped month, not departure.
- Inactive-next customers are chronically low-activity; no visible decline before the event, so "deterioration" visuals are not supported.
- Critical/High/Medium tiers have the same observed rate (~33–35%) vs Low 12.8%: two practical groups, not four.
- Customer profile attributes carry almost no signal; adding them did not improve validation PR-AUC (0.3054 vs 0.3123), supporting the transaction-only model.

## Remaining
- The Power BI generator defines six German-language report pages and 74 visuals. The repository also includes an exported semantic model (`powerbi/model.bim`), DAX definitions, and `scripts/build_powerbi_model.ps1` to update a local PBIX. The binary report is excluded from Git. On a Windows machine with the private inputs, verify the six pages, model refresh and saved file in Power BI Desktop before claiming the dashboard is complete.
- Optional: XGBoost candidate, independent calibration period, decide whether CustomerMonthly load should be disabled (it duplicates ChurnFeatures).
- January 2024 outcomes are unobserved, so December scores cannot be validated.
