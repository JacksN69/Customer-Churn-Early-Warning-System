"""Phase 19: SHAP model-driver explanations (explanatory, not causal).

Validation/test rows are explained with the train-only model that produced their
scores; the December production rows with the production refit. Impacts are in
log-odds units: positive pushes the predicted inactivity probability up.

Outputs:
  outputs/shap_explanations.parquet  (top-3 drivers per scored customer-month)
  outputs/feature_importance.csv     (global mean |SHAP|, test and scoring months)
  outputs/churn_predictions.parquet  (rewritten with TopDriver columns)

Run: python -m src.explainability.shap_explanations
"""
import warnings

import joblib
import numpy as np
import pandas as pd
import shap

warnings.filterwarnings("ignore", category=RuntimeWarning)   # correlation with constant columns -> NaN
warnings.filterwarnings("ignore", message="LightGBM binary classifier with TreeExplainer")

from src import config
from src.models import common
from src.models.predict import MODEL_PATHS

SPLIT_BY_SCORE_TYPE = {"Validation (out-of-sample)": ("validation", "stage_a"),
                       "Test (out-of-sample)": ("test", "stage_a"),
                       "Production (Dec 2023 -> Jan 2024)": ("score", "final")}


def explain(bundle, frame, background):
    model = bundle["model"]
    if bundle["family"] == "lightgbm":
        values = shap.TreeExplainer(model).shap_values(frame)
        if isinstance(values, list):
            values = values[1]
        values = np.asarray(values)
        if values.ndim == 3:
            values = values[:, :, 1]
        return values
    pre = model[:-1]
    explainer = shap.LinearExplainer(model[-1], pre.transform(background))
    return np.asarray(explainer.shap_values(pre.transform(frame)))


def top_drivers(values, frame, k=3):
    features = np.array(frame.columns)
    order = np.argsort(-np.abs(values), axis=1)[:, :k]
    out = {}
    for j in range(k):
        idx = order[:, j]
        out[f"TopDriver{j + 1}"] = features[idx]
        out[f"TopDriver{j + 1}Impact"] = values[np.arange(len(values)), idx]
        out[f"TopDriver{j + 1}Value"] = frame.to_numpy(dtype=float)[np.arange(len(values)), idx]
    return pd.DataFrame(out)


def main():
    sp = common.get_splits()
    bundles = {name: joblib.load(path) for name, path in MODEL_PATHS.items()}
    preds = pd.read_parquet(config.OUTPUTS_DIR / "churn_predictions.parquet")
    preds = preds.drop(columns=[c for c in preds.columns if c.startswith("TopDriver")])
    background = sp.frame("train", bundles["final"]["features"]).sample(2000, random_state=config.RANDOM_STATE)
    explained, importance = [], {}
    for score_type, (split, which) in SPLIT_BY_SCORE_TYPE.items():
        bundle = bundles[which]
        frame = sp.frame(split, bundle["features"])
        values = explain(bundle, frame, background)
        drivers = top_drivers(values, frame)
        drivers.insert(0, "customer_id", sp.parts[split]["customer_id"].astype(str).to_numpy())
        drivers.insert(1, "Month", pd.to_datetime(sp.parts[split]["Month"]).to_numpy())
        drivers.insert(2, "ScoreType", score_type)
        explained.append(drivers)
        if split in ("test", "score"):
            importance[split] = pd.DataFrame({
                "mean_abs_shap": np.abs(values).mean(axis=0),
                "value_shap_correlation": [frame[c].corr(pd.Series(values[:, i], index=frame.index))
                                           for i, c in enumerate(frame.columns)],
            }, index=frame.columns)
        print("explained", score_type, len(frame), flush=True)

    expl = pd.concat(explained, ignore_index=True)
    expl.to_parquet(config.OUTPUTS_DIR / "shap_explanations.parquet", index=False)
    merged = preds.merge(expl, on=["customer_id", "Month", "ScoreType"], how="left", validate="one_to_one")
    assert merged["TopDriver1"].notna().all(), "missing SHAP drivers for some predictions"
    merged.to_parquet(config.OUTPUTS_DIR / "churn_predictions.parquet", index=False)

    fi = pd.DataFrame({
        "feature": importance["test"].index,
        "mean_abs_shap_test": importance["test"]["mean_abs_shap"].to_numpy(),
        "value_shap_correlation_test": importance["test"]["value_shap_correlation"].to_numpy(),
        "mean_abs_shap_scoring": importance["score"]["mean_abs_shap"].reindex(importance["test"].index).to_numpy(),
    }).sort_values("mean_abs_shap_test", ascending=False)
    fi["rank"] = np.arange(1, len(fi) + 1)
    fi["note"] = "mean |SHAP| in log-odds; correlation sign shows how feature values co-move with predicted risk (not causal)"
    fi.to_csv(config.OUTPUTS_DIR / "feature_importance.csv", index=False)
    print(fi.head(12)[["rank", "feature", "mean_abs_shap_test", "value_shap_correlation_test"]].to_string(index=False))


if __name__ == "__main__":
    main()
