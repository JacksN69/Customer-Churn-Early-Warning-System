"""Chronological, leakage-controlled next-month inactivity modeling.

Train T=2023-06..09, select model T=2023-10, final holdout T=2023-11.
Dec 2023 active customers are scored prospectively for Jan 2024 without
claiming to know the Jan outcomes. Customer snapshots are never input.
"""
import csv
import json
import math
from pathlib import Path
import warnings

import duckdb
import joblib
import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score, roc_auc_score, brier_score_loss, log_loss
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
MODELS = ROOT / "models"
DATA = ROOT / "data" / "processed"
for p in (REPORTS, MODELS): p.mkdir(parents=True, exist_ok=True)
PARQUET = DATA / "churn_features.parquet"
REGISTRY = ROOT / "docs" / "FEATURE_REGISTRY.csv"
records = list(csv.DictReader(REGISTRY.open(encoding="utf-8")))
selected = [r["column"] for r in records if r["table"] == "ChurnFeatures"
    and r["historical_ml_policy"] in ("ML_CANDIDATE", "ML_CANDIDATE_WITH_NULL_INDICATOR")]
category = "PreferredTransactionType"
numeric = [c for c in selected if c != category]
if category not in selected: raise ValueError("No transaction type registered")
if any(x in numeric for x in ["InactiveNextMonth","ExtendedInactivityNext3Months","churn_probability"]):
    raise ValueError("Leaky model input in registry")
if len(numeric) < 20: raise ValueError("Too few behavioral features; check registry")

def identifier(s):
    return '"' + s.replace('"','""') + '"'
def sqlpath(p):
    return p.as_posix().replace("'","''")
db = duckdb.connect(":memory:")
cats = ["Transfer", "Payment", "Withdrawal", "Deposit"]
feature_names = numeric + ["PreferredType_" + c for c in cats]
exprs = [f'CAST({identifier(c)} AS DOUBLE) AS {identifier(c)}' for c in numeric]
exprs.extend([
    f"CASE WHEN PreferredTransactionType='{c}' THEN 1.0 ELSE 0.0 END AS {identifier('PreferredType_'+c)}"
    for c in cats
])
sql = f"""
SELECT CAST(customer_id AS VARCHAR) AS customer_id,
       strftime(Month, '%Y-%m') AS period,
       COALESCE(InactiveNextMonth,-1)::INTEGER AS target,
       {','.join(exprs)}
FROM read_parquet('{sqlpath(PARQUET)}')
WHERE EligibleForTraining=1
   OR (Month=DATE '2023-12-01' AND TransactionCount>0 AND Has6MonthHistory=1)
ORDER BY Month,customer_id
"""
arrays = db.execute(sql).fetchnumpy()
n = len(arrays["period"])
periods = np.asarray(arrays["period"]).astype("U7")
ids = np.asarray(arrays["customer_id"]).astype(str)
targets = np.asarray(arrays["target"], dtype=np.int64)
num_features = []
for name in feature_names:
    col = arrays[name]
    x = np.asarray(np.ma.filled(col,np.nan), dtype=np.float64)
    num_features.append(x)
X = np.column_stack(num_features)
if np.isinf(X).any(): raise ValueError("Unexpected infinite feature values")
train = np.isin(periods,["2023-06","2023-07","2023-08","2023-09"])
valid = periods=="2023-10"
test = periods=="2023-11"
december = periods=="2023-12"
for label,mask in [("train",train),("validation",valid),("test",test),("December",december)]:
    if not mask.any(): raise AssertionError("Empty cohort: "+label)
if not np.all(targets[train|valid|test] >= 0): raise AssertionError("Missing observed target")
if not np.all(targets[december] == -1): raise AssertionError("December outcome known or fabricated")
trainX,trainY = X[train],targets[train]
validX,validY = X[valid],targets[valid]
testX,testY = X[test],targets[test]
baseline_rate=float(trainY.mean())

def metrics(y,prob):
    prob=np.asarray(prob,dtype=float)
    if not np.all(np.isfinite(prob)) or np.any((prob<0)|(prob>1)):
        raise ValueError("Invalid risk probabilities")
    row={
        "n":int(len(y)),
        "positive_n":int(y.sum()),
        "positive_rate":float(y.mean()),
        "roc_auc":float(roc_auc_score(y,prob)),
        "pr_auc":float(average_precision_score(y,prob)),
        "brier":float(brier_score_loss(y,prob)),
        "log_loss":float(log_loss(y,np.clip(prob,1e-7,1-1e-7))),
    }
    order=np.argsort(-prob,kind="stable")
    for share in [0.05,0.10]:
        k=max(1,int(np.ceil(len(y)*share)))
        caught=int(np.asarray(y)[order[:k]].sum())
        suffix=str(round(share*100))
        row[f"precision_top{suffix}pct"]=float(caught/k)
        row[f"recall_top{suffix}pct"]=float(caught/int(np.sum(y)))
        row[f"contacts_top{suffix}pct"]=int(k)
        row[f"caught_top{suffix}pct"]=caught
    return row

models = {
 "constant_prevalence":DummyClassifier(strategy="prior"),
 "logistic_regression":Pipeline([
     ("impute",SimpleImputer(strategy="median",add_indicator=True)),
     ("scale",StandardScaler()),
     ("model",LogisticRegression(max_iter=750,C=0.5,random_state=42))
 ]),
 "hist_gradient_boosting":HistGradientBoostingClassifier(
     learning_rate=0.07,max_iter=160,max_leaf_nodes=15,
     min_samples_leaf=80,l2_regularization=5.0,
     early_stopping=False,random_state=42
 ),
}
valid_rows={}
for name,model in models.items():
    print("FITTING",name,flush=True)
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        model.fit(trainX,trainY)
        if seen:
            print("WARNINGS",name,[(str(w.message)) for w in seen][:5],flush=True)
    pred=model.predict_proba(validX)[:,1]
    valid_rows[name]=metrics(validY,pred)
    print("VALID",name,valid_rows[name],flush=True)
# Primary criterion is average precision, secondary precision at top 10%.
candidates=["logistic_regression","hist_gradient_boosting"]
winner=max(candidates,key=lambda name:(
    valid_rows[name]["pr_auc"],valid_rows[name]["precision_top10pct"]))
print("VALIDATION_SELECTION",winner,flush=True)

# Refit selected model on training and validation cohorts without looking at
# test metrics. Evaluate November holdout exactly once.
best=models[winner]
fit_idx=train|valid
print("REFITTING",winner,"ON_JUN_OCT",int(fit_idx.sum()),flush=True)
best.fit(X[fit_idx],targets[fit_idx])
test_prob=best.predict_proba(testX)[:,1]
test_result=metrics(testY,test_prob)
print("NOVEMBER_HOLDOUT",test_result,flush=True)
# Test baseline uses prevalence from train + validation only, no holdout fitting.
baseline_result=metrics(testY,np.full(testY.shape,float(targets[fit_idx].mean())))
# Score December: labels not available. No actual performance can be claimed.
dec_prob=best.predict_proba(X[december])[:,1]
if not np.isfinite(dec_prob).all():raise ValueError("Invalid December risk score")
dec_ids=ids[december].tolist()
assert len(set(dec_ids))==len(dec_ids)
db.execute("""CREATE TEMP TABLE dec_predictions AS
SELECT UNNEST(?::VARCHAR[]) AS customer_id, UNNEST(?::DOUBLE[]) AS risk_score""",
           [dec_ids,dec_prob.astype(float).tolist()])
db.execute(f"""
COPY (
SELECT customer_id,
       DATE '2023-12-01' AS observation_month,
       DATE '2024-01-01' AS predicted_inactivity_month,
       risk_score,
       ROW_NUMBER() OVER (ORDER BY risk_score DESC,customer_id) AS risk_rank,
       CAST(ROW_NUMBER() OVER (ORDER BY risk_score DESC,customer_id) <=
           CEIL(COUNT(*) OVER () * 0.10) AS BOOLEAN) AS top_10pct_outreach_priority,
       '{winner}' AS model_name
FROM dec_predictions
) TO '{sqlpath(DATA/"december_risk_scores.parquet")}'
(FORMAT PARQUET,COMPRESSION ZSTD)
""")
stored=db.execute(
 f"SELECT COUNT(*),MIN(risk_score),MAX(risk_score),AVG(risk_score), "
 f"COUNT(*) FILTER(WHERE top_10pct_outreach_priority) "
 f"FROM read_parquet('{sqlpath(DATA/'december_risk_scores.parquet')}')"
).fetchone()
if stored[0]!=len(dec_ids):raise AssertionError("December output missing scores")
joblib.dump(
 {"model":best,"features":feature_names,"train_periods":"June-October 2023",
  "test_period":"November 2023","target":"InactiveNextMonth","selected_model":winner},
 MODELS / "churn_early_warning.joblib",compress=3
)

# EDA uses all observed label months but never informed model feature selection.
summary = db.execute(f"""
SELECT strftime(Month,'%Y-%m') AS observation_period,
       COUNT(*) FILTER(WHERE EligibleForTraining=1) AS eligible,
       COUNT(*) FILTER(WHERE EligibleForTraining=1 AND InactiveNextMonth=1) AS positives,
       ROUND(100.0*COUNT(*) FILTER(WHERE EligibleForTraining=1 AND InactiveNextMonth=1)/
         NULLIF(COUNT(*) FILTER(WHERE EligibleForTraining=1),0),2) AS percent_inactive
FROM read_parquet('{sqlpath(PARQUET)}')
GROUP BY 1 ORDER BY 1
""").fetchall()
missing_percent = np.isnan(trainX).mean(axis=0)
missing_report=sorted([(feature_names[i],round(float(v*100),2)) for i,v in enumerate(missing_percent) if v>0],
                     key=lambda x:-x[1])
table="\n".join(
f"| {name} | {v['n']:,} | {v['positive_rate']:.1%} | {v['roc_auc']:.4f} | {v['pr_auc']:.4f} | "
f"{v['precision_top10pct']:.1%} | {v['recall_top10pct']:.1%} | {v['brier']:.4f} |"
for name,v in valid_rows.items())
months="\n".join(
 f"| {m} | {e or 0:,} | {pos or 0:,} | {f'{pct:.2f}%' if pct is not None else 'N/A'} |"
 for m,e,pos,pct in summary)
missingtable="\n".join(f"| {col} | {pct}% |" for col,pct in missing_report)
report=f"""# Next-month transactional inactivity: EDA + chronological baseline

**Target:** among customers with activity in month T, zero transactions in T+1,
not confirmed account closure. Training starts after six observed months.
Raw transaction dates determine all predictor values; **no customer snapshot fields**,
`churn_probability`, customer IDs, dates or future labels are model inputs.

## Chronological design
- Training: customer-months June–September 2023 ({train.sum():,} rows).
- Model selection: October 2023 ({valid.sum():,} rows).
- Final refit for the selected model: June–October 2023 ({fit_idx.sum():,} rows).
- One-time holdout: November 2023 ({test.sum():,} rows), predicting December.
- Production-style score: December 2023 ({december.sum():,} active customers),
  predicting January 2024 (**no observed January outcomes**).
- Same customers can appear in different months, matching a repeat-scoring use case.
- Feature imputation for Logistic Regression learns medians **on the training fold
  only**, with missingness indicator columns. HistGradientBoosting handles NaN
  natively; raw missing fields are never overwritten with zero.

## Inactivity label prevalence
| Month T | Eligible rows | Positive rows | Inactivity rate |
|---|---:|---:|---:|
{months}

## Validation model comparison (October)
| Model | N | Actual rate | ROC AUC | PR AUC | Precision @ 10% | Recall @ 10% | Brier |
|---|---:|---:|---:|---:|---:|---:|---:|
{table}

The constant-prevalence baseline assigns identical scores to everyone.
Its top-K precision/recall values from sorting ties are arbitrary, not a usable ranking benchmark.

Selected model (highest validation PR AUC): **{winner}**

## November holdout (one-time evaluation)
| Metric | Selected model | Constant-rate baseline |
|---|---:|---:|
| Observations | {test_result['n']:,} | {baseline_result['n']:,} |
| Observed positive rate | {test_result['positive_rate']:.2%} | {baseline_result['positive_rate']:.2%} |
| ROC AUC | {test_result['roc_auc']:.4f} | {baseline_result['roc_auc']:.4f} |
| PR AUC | {test_result['pr_auc']:.4f} | {baseline_result['pr_auc']:.4f} |
| Brier loss (lower better) | {test_result['brier']:.4f} | {baseline_result['brier']:.4f} |
| Precision @ top 5% | {test_result['precision_top5pct']:.2%} | {baseline_result['precision_top5pct']:.2%} |
| Recall @ top 5% | {test_result['recall_top5pct']:.2%} | {baseline_result['recall_top5pct']:.2%} |
| Precision @ top 10% | {test_result['precision_top10pct']:.2%} | {baseline_result['precision_top10pct']:.2%} |
| Recall @ top 10% | {test_result['recall_top10pct']:.2%} | {baseline_result['recall_top10pct']:.2%} |

## December scoring
- Scored active customers: {stored[0]:,}.
- Mean risk score: {stored[3]:.3%}; range {stored[1]:.3%}–{stored[2]:.3%}.
- Flagged top 10% for hypothetical outreach: {stored[4]:,}.
- Private Parquet: `data/processed/december_risk_scores.parquet`.
- No outreach, customer contact, or message was sent.
- Scores are **experimental**; evaluate calibration and segment stability before
  operational deployment. Risk is predictive association, not causal explanation.

## Missing transaction-derived features in June–September train
| Feature | Training NULL |
|---|---:|
{missingtable if missingtable else '| None | 0% |'}

## Artifacts and caution
- Saved scikit-learn estimator: `models/churn_early_warning.joblib`, local private.
- Predictors ({len(feature_names)}): {', '.join(feature_names)}.
- Full result (numeric values): `reports/model_metrics.json`.
- Model uses all strictly dated transaction-derived predictors and a deterministic
  one-hot of the transaction type category; no raw customer-profile snapshots.
- Dataset is synthetic/portfolio-like unless provenance supports real-world
  operational use; do not advertise evidence of causal churn reduction.
"""
(REPORTS/"eda_and_model_baseline.md").write_text(report,encoding="utf-8")
(REPORTS/"model_metrics.json").write_text(json.dumps({
 "train_rows":int(train.sum()),"validation_rows":int(valid.sum()),
 "test_rows":int(test.sum()),"december_rows":int(december.sum()),
 "feature_names":feature_names,"validation":valid_rows,"selected_model":winner,
 "test":test_result,"test_constant_baseline":baseline_result,"december_mean_risk":stored[3]
},indent=2),encoding="utf-8")
print("MODEL_SUCCESS",winner,"TEST_PR_AUC",test_result["pr_auc"],
      "TEST_PRECISION10",test_result["precision_top10pct"],
      "DECEMBER_ROWS",stored[0],flush=True)
