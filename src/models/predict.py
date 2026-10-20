"""Phases 15-21, 29: model selection, evaluation, operating thresholds, scoring.

Protocol (chronological, no shuffling):
  A. Fit every candidate on TRAIN months, score VALIDATION (Oct).
  B. Select the production model on validation PR-AUC; learn thresholds / risk-tier
     cutoffs on validation only.
  C. Evaluate the selected train-only model once on TEST (Nov) with those thresholds.
  D. Refit the selected configuration on Jun-Nov labelled rows and score the
     operational month (Dec 2023 -> predicts January 2024; outcome unobserved).

Outputs: outputs/churn_predictions.parquet (+ SHAP drivers added by
src/explainability/shap_explanations.py), outputs/model_metrics.json,
reports/model_experiments.csv, reports/model_evaluation.md, models/*.joblib.

Run: python -m src.models.predict
"""
import json

import joblib
import numpy as np
import pandas as pd

from src import config
from src.models import common, evaluate, train_baseline, train_lightgbm

MODEL_PATHS = {"stage_a": config.MODELS_DIR / "churn_stage_a.joblib",
               "final": config.MODELS_DIR / "churn_final.joblib"}


def _prediction_rows(part, p, score_type, model_name, version, cutoffs):
    pref = np.select(
        [part["PreferredType_Transfer"] == 1.0, part["PreferredType_Payment"] == 1.0,
         part["PreferredType_Withdrawal"] == 1.0, part["PreferredType_Deposit"] == 1.0],
        ["Transfer", "Payment", "Withdrawal", "Deposit"],
        default="Transfer",
    )
    df = pd.DataFrame({
        "customer_id": part["customer_id"].astype(str),
        "Month": pd.to_datetime(part["Month"]),
        "ScoreType": score_type,
        "InactiveProbability": np.asarray(p, dtype=float),
        "RiskLevel": evaluate.assign_risk_level(p, cutoffs),
        "TransactionCount": part["TransactionCount"].astype(float),
        "TotalAmount": part["TotalAmount"].astype(float),
        "DaysSinceLastTransaction": part["DaysSinceLastTransaction"].astype(float),
        "TransactionCount_Recent3M": part["TransactionCount_Recent3M"].astype(float),
        "TransactionCount_Previous3M": part["TransactionCount_Previous3M"].astype(float),
        "PreviousTransactionCount": part["PreviousTransactionCount"].astype(float),
        "AvgTransactionCount_3M": part["AvgTransactionCount_3M"].astype(float),
        "AvgTransactionCount_6M": part["AvgTransactionCount_6M"].astype(float),
        "TotalAmount_Recent3M": part["TotalAmount_Recent3M"].astype(float),
        "TransactionCount_3M_ChangePct": part["TransactionCount_3M_ChangePct"].astype(float),
        "TotalAmount_3M_ChangePct": part["TotalAmount_3M_ChangePct"].astype(float),
        "PreferredTransactionType": pref,
        "PaymentCount": part["PaymentCount"].astype(float),
        "TransferCount": part["TransferCount"].astype(float),
        "WithdrawalCount": part["WithdrawalCount"].astype(float),
        "DepositCount": part["DepositCount"].astype(float),
        "ActualInactiveNextMonth": part["target"].astype("Int64"),
        "ModelName": model_name, "ModelVersion": version,
    })
    df["PredictionMonth"] = df["Month"] + pd.DateOffset(months=1)
    df["RiskRank"] = df.groupby("Month")["InactiveProbability"].rank(ascending=False, method="first").astype(int)
    n_month = df.groupby("Month")["InactiveProbability"].transform("count")
    df["RiskDecile"] = np.ceil(df["RiskRank"] * 10.0 / n_month).clip(1, 10).astype(int)
    df["IsTop10PctRank"] = (df["RiskRank"] <= np.ceil(n_month * 0.10)).astype(int)
    df["RiskLevelSort"] = df["RiskLevel"].map({"Critical": 1, "High": 2, "Medium": 3, "Low": 4}).astype(int)
    # Phase 29: value-weighted prioritisation (Recent 3M spend x probability).
    df["PriorityScore"] = df["InactiveProbability"] * df["TotalAmount_Recent3M"]
    high_value = df["TotalAmount_Recent3M"] >= df.groupby("Month")["TotalAmount_Recent3M"].transform("median")
    high_risk = df["RiskLevel"].isin(["Critical", "High"])
    df["PriorityQuadrant"] = np.select(
        [high_value & high_risk, high_value & ~high_risk, ~high_value & high_risk],
        ["High value + High risk", "High value + Low risk", "Low value + High risk"],
        default="Low value + Low risk")
    df["PriorityQuadrantSort"] = df["PriorityQuadrant"].map({
        "High value + High risk": 1, "Low value + High risk": 2,
        "High value + Low risk": 3, "Low value + Low risk": 4,
    }).astype(int)
    return df


def main():
    sp = common.get_splits()
    run_id = common.new_run_id()
    yv, yt = sp.y("validation"), sp.y("test")

    cands = train_baseline.fit_candidates(sp) + train_lightgbm.fit_candidates(sp)
    profile = train_lightgbm.fit_profile_experiment(sp)
    for c in cands + [profile]:
        c["val"] = evaluate.ranking_metrics(yv, c["p_val"])
        print(f"{c['model_name']:<34} val PR-AUC {c['val']['pr_auc']:.4f}  ROC {c['val']['roc_auc']:.4f}  "
              f"P@10% {c['val']['precision_top10']:.3f}", flush=True)

    winner = max([c for c in cands if c["production"]],
                 key=lambda c: (c["val"]["pr_auc"], c["val"]["precision_top10"]))
    version = f"{winner['model_name']}-{run_id}"
    thresholds = evaluate.choose_thresholds(yv, winner["p_val"])
    cutoffs = thresholds["risk_tiers"]["cutoffs"]

    # C. one-time test evaluation with the train-only model and validation-learned thresholds
    test_frame = sp.frame("test")
    p_test = winner["predict"](winner["model"], test_frame)
    test = evaluate.ranking_metrics(yt, p_test)
    at_threshold = {name: evaluate.threshold_metrics(yt, p_test, thresholds[name]["threshold"])
                    for name in ("operating", "f1_optimal", "cost_optimal")}
    calib, ece = evaluate.calibration_table(yt, p_test)
    p_val = winner["p_val"]

    # D. production refit on all labelled months, score December
    labelled = pd.concat([sp.parts["train"], sp.parts["validation"], sp.parts["test"]], ignore_index=True)
    final = winner["refit"](labelled[winner["features"]], labelled["target"].to_numpy(dtype=np.int64))
    p_score = winner["predict"](final, sp.frame("score", winner["features"]))
    score_levels = evaluate.assign_risk_level(p_score, cutoffs)
    score_tier_share = {lvl: float((score_levels == lvl).mean()) for lvl in evaluate.RISK_LEVELS}

    config.OUTPUTS_DIR.mkdir(exist_ok=True)
    config.MODELS_DIR.mkdir(exist_ok=True)
    meta = {"features": winner["features"], "model_name": winner["model_name"], "family": winner["family"],
            "version": version, "cutoffs": cutoffs}
    joblib.dump({**meta, "model": winner["model"]}, MODEL_PATHS["stage_a"], compress=3)
    joblib.dump({**meta, "model": final}, MODEL_PATHS["final"], compress=3)

    preds = pd.concat([
        _prediction_rows(sp.parts["validation"], p_val, "Validation (out-of-sample)", winner["model_name"], version, cutoffs),
        _prediction_rows(sp.parts["test"], p_test, "Test (out-of-sample)", winner["model_name"], version, cutoffs),
        _prediction_rows(sp.parts["score"], p_score, "Production (Dec 2023 -> Jan 2024)", winner["model_name"], version, cutoffs),
    ], ignore_index=True)
    preds.to_parquet(config.OUTPUTS_DIR / "churn_predictions.parquet", index=False)

    metrics = {
        "run_id": run_id,
        "target": "InactiveNextMonth: next-month transactional inactivity (not confirmed account closure)",
        "model": {"name": winner["model_name"], "family": winner["family"], "version": version,
                  "feature_set": winner["feature_set"], "n_features": len(winner["features"]),
                  "parameters": winner["params"], "probabilities_calibrated_by_design": bool(winner["calibrated"])},
        "windows": {"train": common.period_text(config.TRAIN_MONTHS), "validation": common.period_text(config.VALIDATION_MONTHS),
                    "test": common.period_text(config.TEST_MONTHS), "scoring_month": config.SCORING_MONTH,
                    "prediction_month": config.PREDICTION_MONTH,
                    "production_refit": f"{config.TRAIN_MONTHS[0]}..{config.TEST_MONTHS[-1]}"},
        "rows": {k: int(len(sp.parts[k])) for k in ("train", "validation", "test", "score")},
        "selection": "highest validation PR-AUC among production-eligible candidates (test month untouched)",
        "validation_candidates": {c["model_name"]: {**c["val"], "feature_set": c["feature_set"],
                                                   "production_eligible": c["production"]} for c in cands + [profile]},
        "test": {**test, "constant_prevalence_pr_auc": test["prevalence"]},
        "test_at_thresholds": at_threshold,
        "thresholds_learned_on_validation": thresholds,
        "risk_tiers": {"validation": evaluate.tier_table(yv, p_val, cutoffs), "test": evaluate.tier_table(yt, p_test, cutoffs)},
        "calibration_test": {"deciles_high_to_low": calib, "expected_calibration_error": ece},
        "scoring": {"customers": int(len(p_score)), "mean_probability": float(np.mean(p_score)),
                    "risk_level_share": score_tier_share,
                    "note": "Tier cutoffs come from validation scores of the train-only model; December uses a "
                            "refit model, so shares can drift from the 5/5/20/70% design"},
        "limitations": ["January 2024 outcomes are unobserved: December scores are unverified prospective scores",
                        "No confirmed account-closure label; target is transactional inactivity",
                        "About 73% of inactive-next-month customer-months are active again at T+2 (transient gaps, see EDA)",
                        "SHAP/permutation results describe the model, not causal drivers"],
    }
    warnings = []
    if not winner["calibrated"]:
        warnings.append("Class-weighted model selected: probabilities are not calibrated")
    t_tiers = {r["risk_level"]: r["observed_inactive_rate"] for r in metrics["risk_tiers"]["test"]}
    if t_tiers["Critical"] - t_tiers["Medium"] < 0.03:
        warnings.append(
            "Critical/High/Medium tiers have practically the same observed inactivity rate on the test month "
            f"({t_tiers['Critical']:.1%} / {t_tiers['High']:.1%} / {t_tiers['Medium']:.1%} vs Low {t_tiers['Low']:.1%}). "
            "The model separates an elevated-risk group from the rest but not risk levels within it; treat "
            "Medium+ as one elevated group and use probability/PriorityScore for ordering inside it")
    if warnings:
        metrics["warnings"] = warnings
    (config.OUTPUTS_DIR / "model_metrics.json").write_text(json.dumps(metrics, indent=2, default=float), encoding="utf-8")

    # Experiment log (test metrics only for the selected model)
    rows = []
    for c in cands + [profile]:
        v = c["val"]
        row = {"run_id": run_id, "model_name": c["model_name"], "feature_set": c["feature_set"],
               "n_features": len(c["features"]), "train_period": common.period_text(config.TRAIN_MONTHS),
               "validation_period": common.period_text(config.VALIDATION_MONTHS),
               "test_period": common.period_text(config.TEST_MONTHS),
               "parameters": json.dumps(c["params"], default=str), "selected": c is winner,
               "val_roc_auc": round(v["roc_auc"], 5), "val_pr_auc": round(v["pr_auc"], 5),
               "val_precision_top10": round(v["precision_top10"], 5), "val_recall_top10": round(v["recall_top10"], 5),
               "val_precision_top5": round(v["precision_top5"], 5), "val_recall_top5": round(v["recall_top5"], 5),
               "notes": c.get("notes", "")}
        if c is winner:
            op = at_threshold["operating"]
            row.update({"test_roc_auc": round(test["roc_auc"], 5), "test_pr_auc": round(test["pr_auc"], 5),
                        "test_precision": round(op["precision"], 5), "test_recall": round(op["recall"], 5),
                        "test_f1": round(op["f1"], 5), "test_precision_top10": round(test["precision_top10"], 5),
                        "test_recall_top10": round(test["recall_top10"], 5),
                        "test_precision_top5": round(test["precision_top5"], 5),
                        "test_recall_top5": round(test["recall_top5"], 5)})
        rows.append(row)
    common.log_experiments(rows)
    write_report(metrics, calib, ece)
    print("SELECTED", winner["model_name"], "| TEST PR-AUC", round(test["pr_auc"], 4), "ROC", round(test["roc_auc"], 4),
          "| P@10%", round(test["precision_top10"], 4), "| December scored", len(p_score), flush=True)
    return metrics


def write_report(m, calib, ece):
    t = m["test"]
    lines = [f"# Model evaluation (run {m['run_id']})", "",
             f"**Target:** {m['target']}.", "",
             f"**Selected model:** `{m['model']['name']}` ({m['model']['n_features']} features, version `{m['model']['version']}`).",
             f"Selection: {m['selection']}.", "",
             "## Chronological design", "",
             f"- Train {m['windows']['train']} ({m['rows']['train']:,} rows), validation {m['windows']['validation']} "
             f"({m['rows']['validation']:,}), test {m['windows']['test']} ({m['rows']['test']:,}).",
             f"- Production refit {m['windows']['production_refit']}; scored {m['windows']['scoring_month']} "
             f"({m['rows']['score']:,} customers) for {m['windows']['prediction_month']} (unobserved).", "",
             "## Validation comparison (October)", "",
             "| Model | Feature set | ROC-AUC | PR-AUC | P@5% | R@5% | P@10% | R@10% | Eligible |", "|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for name, v in m["validation_candidates"].items():
        lines.append(f"| {name} | {v['feature_set']} | {v['roc_auc']:.4f} | {v['pr_auc']:.4f} | {v['precision_top5']:.3f} | "
                     f"{v['recall_top5']:.3f} | {v['precision_top10']:.3f} | {v['recall_top10']:.3f} | "
                     f"{'yes' if v['production_eligible'] else 'experiment only'} |")
    lines += ["", "## Test (November, evaluated once)", "",
              f"Prevalence {t['prevalence']:.2%} (a constant-score model has PR-AUC = prevalence).", "",
              "| Metric | Value |", "|---|---:|",
              f"| ROC-AUC | {t['roc_auc']:.4f} |", f"| PR-AUC | {t['pr_auc']:.4f} |", f"| Brier | {t['brier']:.4f} |",
              f"| Precision@Top5% / Recall@Top5% | {t['precision_top5']:.3f} / {t['recall_top5']:.3f} (lift {t['lift_top5']:.2f}x) |",
              f"| Precision@Top10% / Recall@Top10% | {t['precision_top10']:.3f} / {t['recall_top10']:.3f} (lift {t['lift_top10']:.2f}x) |",
              f"| Expected calibration error | {ece:.4f} |", "",
              "## Operating thresholds (learned on validation, applied to test)", "",
              "| Rule | Threshold | Flagged | Precision | Recall | F1 | TN | FP | FN | TP |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, r in m["test_at_thresholds"].items():
        cm = r["confusion_matrix"]
        lines.append(f"| {name}: {m['thresholds_learned_on_validation'][name]['rule']} | {r['threshold']:.4f} | "
                     f"{r['flagged_share']:.1%} | {r['precision']:.3f} | {r['recall']:.3f} | {r['f1']:.3f} | "
                     f"{cm['tn']:,} | {cm['fp']:,} | {cm['fn']:,} | {cm['tp']:,} |")
    lines += ["", "**Chosen operating threshold:** the capacity rule (top 10% of active customers), because outreach "
              "volume is limited by retention-team capacity. The F1 and cost rules are shown for comparison; the "
              "cost rule uses placeholder unit costs.", "",
              "## Risk tiers (cutoffs from validation)", "",
              "| Level | Test customers | Test share | Observed inactive rate | Validation observed rate |", "|---|---:|---:|---:|---:|"]
    for a, b in zip(m["risk_tiers"]["test"], m["risk_tiers"]["validation"]):
        lines.append(f"| {a['risk_level']} | {a['customers']:,} | {a['share']:.1%} | {a['observed_inactive_rate']:.1%} | "
                     f"{b['observed_inactive_rate']:.1%} |")
    lines += ["", "## Calibration by decile (test, highest risk first)", "",
              "| Decile | Customers | Observed | Mean predicted |", "|---|---:|---:|---:|"]
    lines += [f"| {r['decile']} | {r['customers']:,} | {r['observed']:.1%} | {r['mean_predicted']:.1%} |" for r in calib]
    s = m["scoring"]
    lines += ["", "## December scoring (unverified)", "",
              f"{s['customers']:,} customers, mean probability {s['mean_probability']:.2%}. Risk shares: " +
              ", ".join(f"{k} {v:.1%}" for k, v in s["risk_level_share"].items()) + ".", "",
              "## Limitations", ""] + [f"- {x}" for x in m["limitations"]] + (
                  ["", "## Warnings", ""] + [f"- {x}" for x in m.get("warnings", [])] if m.get("warnings") else [])
    (config.REPORTS_DIR / "model_evaluation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
