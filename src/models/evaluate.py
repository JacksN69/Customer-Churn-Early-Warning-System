"""Evaluation utilities: ranking metrics, threshold selection, risk tiers, calibration.

Thresholds and tier cutoffs are chosen on the VALIDATION month only and then
applied unchanged to the test month and to the scoring month.
"""
import math

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, precision_recall_curve, roc_auc_score

from src import config

RISK_LEVELS = ["Low", "Medium", "High", "Critical"]


def ranking_metrics(y, p):
    y = np.asarray(y)
    p = np.asarray(p, dtype=float)
    if not np.all(np.isfinite(p)) or p.min() < 0 or p.max() > 1:
        raise ValueError("Invalid probabilities")
    out = {
        "n": int(len(y)), "positives": int(y.sum()), "prevalence": float(y.mean()),
        "roc_auc": float(roc_auc_score(y, p)), "pr_auc": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "log_loss": float(log_loss(y, np.clip(p, 1e-7, 1 - 1e-7))),
    }
    order = np.argsort(-p, kind="stable")
    for share in (0.05, 0.10):
        k = max(1, math.ceil(len(y) * share))
        caught = int(y[order[:k]].sum())
        tag = f"top{round(share * 100)}"
        out[f"precision_{tag}"] = caught / k
        out[f"recall_{tag}"] = caught / int(y.sum())
        out[f"lift_{tag}"] = (caught / k) / float(y.mean())
        out[f"contacts_{tag}"] = k
    return out


def threshold_metrics(y, p, threshold):
    y = np.asarray(y)
    pred = (np.asarray(p) >= threshold).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"threshold": float(threshold), "flagged_share": float(pred.mean()),
            "precision": precision, "recall": recall, "f1": f1,
            "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp}}


def capacity_cutoff(p, share):
    """Probability cutoff such that (at least) the top `share` of customers are flagged."""
    p = np.sort(np.asarray(p, dtype=float))[::-1]
    k = max(1, math.ceil(len(p) * share))
    return float(p[k - 1])


def choose_thresholds(y_val, p_val):
    """Candidate operating thresholds learned on validation data."""
    y_val = np.asarray(y_val)
    prec, rec, thr = precision_recall_curve(y_val, p_val)
    f1 = 2 * prec[:-1] * rec[:-1] / np.clip(prec[:-1] + rec[:-1], 1e-12, None)
    f1_thr = float(thr[int(np.argmax(f1))])
    grid = np.unique(np.quantile(p_val, np.linspace(0.0, 0.999, 400)))
    costs = []
    for t in grid:
        m = threshold_metrics(y_val, p_val, t)["confusion_matrix"]
        costs.append(m["fn"] * config.COST_MISSED_INACTIVE + m["fp"] * config.COST_UNNEEDED_CONTACT)
    cost_thr = float(grid[int(np.argmin(costs))])
    capacity_thr = capacity_cutoff(p_val, config.OPERATING_CAPACITY)
    tiers = {name: capacity_cutoff(p_val, share) for name, share in config.RISK_TIER_CAPACITY.items()}
    return {
        "operating": {"rule": f"top {config.OPERATING_CAPACITY:.0%} of active customers (retention capacity)",
                      "threshold": capacity_thr},
        "f1_optimal": {"rule": "maximises F1 on validation", "threshold": f1_thr},
        "cost_optimal": {"rule": f"minimises {config.COST_MISSED_INACTIVE:g} x missed + "
                                 f"{config.COST_UNNEEDED_CONTACT:g} x unneeded contacts on validation "
                                 "(placeholder costs, replace with business values)", "threshold": cost_thr},
        "risk_tiers": {"rule": "cumulative capacity shares " + ", ".join(
            f"{k} top {v:.0%}" for k, v in config.RISK_TIER_CAPACITY.items()), "cutoffs": tiers},
    }


def assign_risk_level(p, cutoffs):
    p = np.asarray(p, dtype=float)
    return np.select([p >= cutoffs["Critical"], p >= cutoffs["High"], p >= cutoffs["Medium"]],
                     ["Critical", "High", "Medium"], default="Low")


def tier_table(y, p, cutoffs):
    levels = assign_risk_level(p, cutoffs)
    y = np.asarray(y)
    rows = []
    for lvl in reversed(RISK_LEVELS):
        m = levels == lvl
        rows.append({"risk_level": lvl, "customers": int(m.sum()), "share": float(m.mean()),
                     "observed_inactive_rate": float(y[m].mean()) if m.any() else None,
                     "mean_predicted": float(np.asarray(p)[m].mean()) if m.any() else None})
    return rows


def calibration_table(y, p, bins=10):
    y = np.asarray(y)
    p = np.asarray(p, dtype=float)
    order = np.argsort(-p, kind="stable")
    rows, ece = [], 0.0
    for i, idx in enumerate(np.array_split(order, bins), 1):
        obs, pred = float(y[idx].mean()), float(p[idx].mean())
        ece += len(idx) * abs(obs - pred) / len(y)
        rows.append({"decile": i, "customers": int(len(idx)), "observed": obs, "mean_predicted": pred})
    return rows, float(ece)

