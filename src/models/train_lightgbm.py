"""Phase 16: LightGBM candidates.

A small, fixed set of configurations is trained on the training months with early
stopping on the VALIDATION month (PR-AUC). The test month is never used here.
A "behavior+static_profile" variant is trained only as a clearly labelled
experiment (undated customer snapshot fields; never selectable for production).

Run: python -m src.models.train_lightgbm
"""
import lightgbm as lgb
import pandas as pd

from src import config
from src.models import common, evaluate

BASE_PARAMS = dict(objective="binary", subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                   reg_lambda=5.0, random_state=config.RANDOM_STATE, n_jobs=4, verbose=-1)
CONFIGS = {
    "lightgbm_leaves31": dict(learning_rate=0.05, num_leaves=31, min_child_samples=100),
    "lightgbm_leaves15": dict(learning_rate=0.03, num_leaves=15, min_child_samples=200),
    "lightgbm_leaves31_pos_weight": dict(learning_rate=0.05, num_leaves=31, min_child_samples=100,
                                         scale_pos_weight=4.0),
}
MAX_TREES = 1500
REFIT_TREE_SCALE = 1.2   # production refit sees ~1.2-1.5x more months than the train-only fit


def _fit(params, X, y, X_val, y_val):
    model = lgb.LGBMClassifier(n_estimators=MAX_TREES, **BASE_PARAMS, **params)
    model.fit(X, y, eval_X=X_val, eval_y=y_val, eval_metric="binary_logloss",
              callbacks=[lgb.early_stopping(60, verbose=False)])
    return model


def _candidate(name, params, sp, features, feature_set, production, frame_fn=None):
    frame = frame_fn or (lambda split: sp.frame(split, features))
    model = _fit(params, frame("train"), sp.y("train"), frame("validation"), sp.y("validation"))
    best_iter = int(model.best_iteration_ or MAX_TREES)

    def refit(X, y, params=params, best_iter=best_iter):
        m = lgb.LGBMClassifier(n_estimators=max(50, int(best_iter * REFIT_TREE_SCALE)), **BASE_PARAMS, **params)
        return m.fit(X, y)

    return {
        "model_name": name, "family": "lightgbm", "feature_set": feature_set, "features": features,
        "params": {**params, "best_iteration": best_iter}, "model": model, "production": production,
        "calibrated": "pos_weight" not in name, "refit": refit,
        "p_val": model.predict_proba(frame("validation"))[:, 1],
        "predict": lambda m, frame_: m.predict_proba(frame_)[:, 1],
    }


def fit_candidates(sp):
    out = [_candidate(n, p, sp, sp.features, "behavior", True) for n, p in CONFIGS.items()]
    return out


def profile_splits(sp):
    """Splits with static customer-profile columns appended (experiment only)."""
    dim = pd.read_parquet(config.DIM_CUSTOMER, columns=["customer_id"] + config.PROFILE_EXPERIMENT_COLUMNS)
    df = sp.df.merge(dim, on="customer_id", how="left", validate="many_to_one")
    for col in config.PROFILE_EXPERIMENT_COLUMNS:
        if not pd.api.types.is_numeric_dtype(df[col]):
            df[col] = df[col].astype("category")
    return common.Splits(df, sp.features + config.PROFILE_EXPERIMENT_COLUMNS)


def fit_profile_experiment(sp):
    sp2 = profile_splits(sp)
    cand = _candidate("lightgbm_leaves31_with_profile", CONFIGS["lightgbm_leaves31"], sp2, sp2.features,
                      "behavior+static_profile", False)
    cand["notes"] = ("EXPERIMENT ONLY: static profile fields are undated snapshots; not eligible for production "
                     "until their as-of availability is established")
    return cand


if __name__ == "__main__":
    sp = common.get_splits()
    for c in fit_candidates(sp) + [fit_profile_experiment(sp)]:
        m = evaluate.ranking_metrics(sp.y("validation"), c["p_val"])
        print(c["model_name"], c["params"].get("best_iteration"),
              {k: round(v, 4) for k, v in m.items() if k in ("roc_auc", "pr_auc", "precision_top10")})
