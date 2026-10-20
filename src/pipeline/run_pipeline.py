"""One command to regenerate everything: raw audit -> ETL -> validation -> ML dataset ->
models -> predictions -> SHAP -> Power BI-ready outputs.

    python -m src.pipeline.run_pipeline              # full run
    python -m src.pipeline.run_pipeline --skip-etl   # reuse existing data/processed Parquet
                                                     # (use while Power BI Desktop has the files open)
    python -m src.pipeline.run_pipeline --from-stage ml_dataset
"""
import argparse
import time

from src.data import build_customer_month, validate_raw
from src.explainability import shap_explanations
from src.features import build_features, validate_features
from src.models import predict


def _validate():
    _, failed = validate_features.run(verbose=False)
    if failed:
        raise SystemExit(f"Feature validation failed: {failed}")


STAGES = [
    ("raw_audit", validate_raw.main, True),
    ("etl", build_customer_month.main, True),
    ("feature_validation", _validate, False),
    ("ml_dataset", build_features.build, False),
    ("models_and_predictions", predict.main, False),
    ("shap", shap_explanations.main, False),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-etl", action="store_true", help="skip raw audit and Parquet rebuild")
    ap.add_argument("--from-stage", choices=[s[0] for s in STAGES])
    args = ap.parse_args()
    started = args.from_stage is None
    for name, fn, is_etl in STAGES:
        if name == args.from_stage:
            started = True
        if not started or (args.skip_etl and is_etl):
            print(f"[skip] {name}")
            continue
        t0 = time.time()
        print(f"[run ] {name}", flush=True)
        fn()
        print(f"[done] {name} ({time.time() - t0:.0f}s)", flush=True)
    print("Pipeline complete. Outputs: outputs/*.parquet|json|csv, reports/model_evaluation.md, reports/model_experiments.csv")


if __name__ == "__main__":
    main()

