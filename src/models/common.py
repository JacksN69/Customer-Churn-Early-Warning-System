"""Shared data access for model training: chronological splits and experiment logging."""
import csv
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from src import config
from src.features.build_features import load_dataset

EXPERIMENT_LOG = config.REPORTS_DIR / "model_experiments.csv"
EXPERIMENT_FIELDS = [
    "run_id", "model_name", "feature_set", "n_features", "train_period", "validation_period", "test_period",
    "parameters", "selected", "val_roc_auc", "val_pr_auc", "val_precision_top10", "val_recall_top10",
    "val_precision_top5", "val_recall_top5", "test_roc_auc", "test_pr_auc", "test_precision", "test_recall",
    "test_f1", "test_precision_top10", "test_recall_top10", "test_precision_top5", "test_recall_top5", "notes",
]


@dataclass
class Splits:
    df: pd.DataFrame
    features: list
    parts: dict = field(default_factory=dict)

    def __post_init__(self):
        for name in ("train", "validation", "test", "score"):
            self.parts[name] = self.df[self.df["split"] == name].reset_index(drop=True)

    def X(self, split, features=None):
        return self.parts[split][features or self.features].to_numpy(dtype=np.float64)

    def frame(self, split, features=None):
        return self.parts[split][features or self.features]

    def y(self, split):
        return self.parts[split]["target"].to_numpy(dtype=np.int64)


def get_splits():
    df, features = load_dataset()
    assert set(features).isdisjoint(config.NEVER_FEATURES), "leaky feature in model inputs"
    return Splits(df, features)


def period_text(months):
    return f"{months[0]}..{months[-1]}" if len(months) > 1 else months[0]


def log_experiments(rows):
    """Append rows (dicts) to reports/model_experiments.csv, creating it if needed."""
    config.REPORTS_DIR.mkdir(exist_ok=True)
    new = not EXPERIMENT_LOG.exists()
    with EXPERIMENT_LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=EXPERIMENT_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows(rows)


def new_run_id():
    return datetime.now().strftime("%Y%m%d-%H%M%S")
