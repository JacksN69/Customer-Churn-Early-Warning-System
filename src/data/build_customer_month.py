"""Phase 3 wrapper: customer audit + DuckDB ETL to customer_monthly / churn_features / dim_customer Parquet.

The SQL lives in src/features/*.sql; scripts/build_parquet_pipeline.py executes it with row-count,
amount and key gates and writes the three Parquet files.
"""
import runpy

from src import config


def main():
    for name in ("audit_customer.py", "build_parquet_pipeline.py", "generate_feature_registry.py"):
        runpy.run_path(str(config.PROJECT_ROOT / "scripts" / name), run_name="__main__")


if __name__ == "__main__":
    main()

