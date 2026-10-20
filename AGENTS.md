# Repository Guidelines

## Project Structure & Module Organization

This project builds a customer churn early-warning report using Python, DuckDB, Power Query, and Power BI.

- `data/raw/`: source customer and transaction CSVs. Preserve these inputs.
- `scripts/audit_raw.py`: audits transactions and generates `reports/data_quality_raw.md`.
- `powerquery/`: active M queries for CSV staging and Parquet imports; original long transformations archived under `powerquery/legacy/`.
- `src/features/*.sql`: validated DuckDB customer-month scaffold and churn feature definitions.
- `scripts/build_parquet_pipeline.py`: reproducible ETL, writes processed monthly/features/dimension Parquet.
- `scripts/audit_customer.py`: audits DimCustomer source grain, missingness and key coverage.
- `docs/FEATURE_REGISTRY.csv`: leakage and availability policy per feature.
- `powerbi/Customer Churn Early-Warning System.pbix`: Power BI report and model.
- `reports/`: generated Markdown audit results.
- `.venv/` and `scripts/.venv/`: local Python environments; exclude them from contributions.

## Build, Test, and Development Commands

Run commands from the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install duckdb
.\.venv\Scripts\python.exe scripts\audit_raw.py
```

Dependencies are pinned in `requirements.txt`. The reproducible audit and ETL run with:

```powershell
.\.venv\Scripts\python.exe scripts\audit_customer.py
.\.venv\Scripts\python.exe scripts\build_parquet_pipeline.py
.\.venv\Scripts\python.exe scripts\generate_feature_registry.py
```

The saved PBIX was migrated to Parquet and verified after closing/reopening. It reads `data/processed/{customer_monthly,churn_features,dim_customer}.parquet` from this PC's absolute Windows project directory. Named CSV source expressions now use `data/raw`. If the workspace moves to a different PC, rebind absolute Windows paths before refreshing.

## Coding Style & Naming Conventions

Use four-space indentation in Python and M. Use `snake_case` for Python variables and scripts, and uppercase names for path constants. Resolve Python paths relative to `PROJECT_ROOT`. Follow existing descriptive PascalCase M steps and feature columns, such as `AddInactiveFlag` and `TransactionCount`. Preserve source field names such as `customer_id`. No formatter or linter is configured.

## Testing Guidelines

No automated test framework or coverage threshold exists. After audit changes, run the script and review counts, nulls, transaction types, amounts, and duplicates in the generated report. After M changes, refresh Power BI and verify customer-month uniqueness, inactive months, historical windows, and null/zero handling. Keep features restricted to information available by the observation month. Export updated M queries alongside `.pbix` changes.

## Commit & Pull Request Guidelines

This checkout has no Git metadata, so historical commit conventions cannot be verified. Use concise imperative subjects, for example `Fix inactive-month feature calculation`. Describe the change, validation performed, and metric or schema effects in each PR. Link relevant issues and include screenshots for report layout changes.

## Data & Configuration Safety

Keep customer-level records and credentials out of PR descriptions and screenshots. Do not automatically remove identical transactions: the source lacks unique transaction IDs, so matching rows may be legitimate.
