"""Phase 15: transparent Logistic Regression baselines.

Numeric features -> median imputation (fit on the training fold only) -> standardisation
-> LogisticRegression. The only categorical input (PreferredTransactionType) is already
one-hot encoded in the ML dataset, with an explicit zero vector for missing values.
Unweighted and class_weight="balanced" variants are both recorded.

Run: python -m src.models.train_baseline   (trains on train, scores validation, logs experiments)
"""
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src import config
from src.models import common, evaluate

FEATURE_SET = "behavior"


def make_logistic(class_weight=None):
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("model", LogisticRegression(C=0.5, max_iter=2000, class_weight=class_weight,
                                     random_state=config.RANDOM_STATE)),
    ])


def fit_candidates(sp):
    """Fit on the training months; return candidates with validation scores."""
    out = []
    for cw in (None, "balanced"):
        name = "logistic_regression" if cw is None else "logistic_regression_balanced"
        model = make_logistic(cw).fit(sp.frame("train"), sp.y("train"))
        out.append({
            "model_name": name, "family": "logistic_regression", "feature_set": FEATURE_SET,
            "features": sp.features, "params": {"C": 0.5, "class_weight": cw, "impute": "median", "scale": "standard"},
            "model": model, "production": True, "calibrated": cw is None,
            "refit": lambda X, y, cw=cw: make_logistic(cw).fit(X, y),
            "p_val": model.predict_proba(sp.frame("validation"))[:, 1],
            "predict": lambda m, frame: m.predict_proba(frame)[:, 1],
        })
    return out


if __name__ == "__main__":
    sp = common.get_splits()
    for c in fit_candidates(sp):
        m = evaluate.ranking_metrics(sp.y("validation"), c["p_val"])
        print(c["model_name"], {k: round(v, 4) for k, v in m.items() if k in ("roc_auc", "pr_auc", "precision_top10")})
