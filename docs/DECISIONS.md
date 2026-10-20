# Decisions

## Target and scope
- Primary target `InactiveNextMonth`: among customer-months active in T, 1 if transactions in T+1 equal zero; 0 if activity continues; null if next month not observed or T is inactive.
- Secondary descriptive target `ExtendedInactivityNext3Months`: active T, no transactions in three subsequent observed months. Never an ML input.
- `customer_data[churn_probability]` is forbidden as label or input.
- Eligible history: at least six observed months inclusive of T; active at T; future T+1 observed.
- Always process customer months in ascending Month order per customer.
- Never use future month data as features. Future data is only for labels.
- Preserve undefined percentage growth as null when previous denominator is zero; add an indicator at ML feature engineering.

## Engineering
- Preserve raw CSV data and possible legitimate exact duplicate transactions.
- Treat raw transactions as authoritative for behavioral features.
- Build independent reference tests and compare actual Power Query outputs before migration.
- Use chronological splits and select a model threshold based on retention capacity, not arbitrary 0.5.
- Explain predictions as model drivers, not causes.
- Scripts, full ETL, validations and reproducibility checks should be executed directly when accessible; no Codex-credit efficiency constraint.
- On Oct 12, 2026, migrated the validated model from M aggregations to DuckDB/Parquet. Backup and prior M logic preserved.
- Power BI's stored `AverageAmount` rounds to a whole number; DuckDB replicates this in the final Parquet export after a failed initial parity check exposed the difference.
- Exact raw/project file paths and all current loaded-model columns were validated on reopening PBIX.
- Customer snapshot columns remain BI-descriptive only until their historical as-of availability is established.

## 2026-10-16 decisions
- Main model stays **transaction-only**. Static profile fields are trained only as a labelled experiment (validation PR-AUC 0.3054 vs 0.3123, no benefit) and are not production-eligible.
- `ObservedTenureMonths` is excluded: it is a calendar proxy (left-censored window) and its test/scoring values fall outside the training range.
- Splits: train Jun–Sep, validation Oct, test Nov (evaluated once); December is the unlabelled scoring month; production model refit on Jun–Nov.
- Thresholds, risk-tier cutoffs and the operating point are learned on validation only. Operating point = top 10% of active customers (retention capacity). Cost-based threshold uses placeholder costs (5 x missed : 1 x contact) until real costs are supplied.
- Registry file keeps the name `docs/FEATURE_REGISTRY.csv` (referenced by AGENTS.md); an explicit `ml_allowed` column was added.
- `CustomerMonthly` stays loaded in Power BI (cheap, referenced by validation DAX); it duplicates a subset of `ChurnFeatures`.
- No GitHub remote. The repository is initialised locally only.
