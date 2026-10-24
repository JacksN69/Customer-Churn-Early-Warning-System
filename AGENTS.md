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
- `powerbi/Customer Churn Early-Warning System.pbix`: local Power BI report (not committed because it may include customer records).
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

The local PBIX uses Parquet files from `data/processed/` and CSV files from `data/raw/`. The repository does not contain the binary PBIX or private source data. Set up the local inputs and rebind Power Query paths when moving to another computer; verify the model after refreshing and reopening Power BI Desktop.

## Coding Style & Naming Conventions

Use four-space indentation in Python and M. Use `snake_case` for Python variables and scripts, and uppercase names for path constants. Resolve Python paths relative to `PROJECT_ROOT`. Follow existing descriptive PascalCase M steps and feature columns, such as `AddInactiveFlag` and `TransactionCount`. Preserve source field names such as `customer_id`. No formatter or linter is configured.

## Testing Guidelines

Pytest tests are in `tests/`; no minimum coverage percentage is enforced. Run `python -m pytest tests` from the project root. Tests that require private CSV or Parquet inputs are skipped when those files are unavailable: report both passed and skipped counts. After M changes, refresh Power BI and verify customer-month uniqueness, inactive months, historical windows, and null/zero handling. Keep all prediction features restricted to information available by the observation month. Export updated M queries alongside local `.pbix` changes.

## Commit & Pull Request Guidelines

Use concise imperative commit subjects, for example `Fix inactive-month feature calculation`. Describe the change, validation performed, and metric or schema effects in each PR. Link relevant issues and include screenshots for report layout changes.

## Data & Configuration Safety

Keep customer-level records and credentials out of PR descriptions and screenshots. Do not automatically remove identical transactions: the source lacks unique transaction IDs, so matching rows may be legitimate.
