"""Holdout calibration and diagnostic permutation importance (no retraining).

These analyses are descriptive diagnostics, not grounds for tuning to the
November holdout; the model was selected on October validation.
"""
from pathlib import Path
import csv
import numpy as np
import duckdb
import joblib
from sklearn.metrics import average_precision_score, brier_score_loss

R=Path(__file__).resolve().parents[1]
cfg=joblib.load(R/"models"/"churn_early_warning.joblib")
model=cfg["model"]; features=cfg["features"]
raw=(R/"data"/"processed"/"churn_features.parquet").as_posix().replace("'","''")
con=duckdb.connect(":memory:")
groups=[f"CAST(\"{f}\" AS DOUBLE) AS \"{f}\"" for f in features if not f.startswith("PreferredType_")]
for cat in ["Transfer","Payment","Withdrawal","Deposit"]:
    groups.append(f"CASE WHEN PreferredTransactionType='{cat}' THEN 1.0 ELSE 0.0 END AS PreferredType_{cat}")
q=f"""SELECT COALESCE(InactiveNextMonth,-1)::INTEGER AS y,
{','.join(groups)} FROM read_parquet('{raw}')
WHERE Month=DATE '2023-11-01' AND EligibleForTraining=1
ORDER BY customer_id"""
cols=con.execute(q).fetchnumpy()
X=np.column_stack([np.asarray(np.ma.filled(cols[f],np.nan),dtype=np.float64) for f in features])
y=np.asarray(cols["y"],dtype=np.int64)
p=model.predict_proba(X)[:,1]
ap=average_precision_score(y,p)
order=np.argsort(-p,kind="stable")
deciles=np.array_split(order,10)
dec_report=[]
for i,idx in enumerate(deciles,1):
    dec_report.append((i,len(idx),float(np.mean(y[idx])),float(np.mean(p[idx])),
                       float(np.mean(y[idx]) / (np.mean(p[idx])+1e-12))))
ece=sum(n*abs(actual-forecast) for _,n,actual,forecast,_ in dec_report)/len(y)
# Feature importance on 8,000 deterministically sampled holdout rows, 2 repetitions.
# Permuting a column leaves correlated peers intact, so do not interpret as causal.
rng=np.random.default_rng(42)
sample=rng.choice(len(y),size=min(8000,len(y)),replace=False)
sx=X[sample].copy(); sy=y[sample]
base_ap=average_precision_score(sy,model.predict_proba(sx)[:,1])
perm=[]
for i,name in enumerate(features):
    deltas=[]
    for j in range(2):
        changed=sx.copy()
        changed[:,i]=changed[rng.permutation(len(sample)),i]
        shifted=average_precision_score(sy,model.predict_proba(changed)[:,1])
        deltas.append(base_ap-shifted)
    perm.append((name,float(np.mean(deltas))))
perm.sort(key=lambda x:x[1],reverse=True)
cal_rows="\n".join(f"| {d} | {n:,} | {actual:.1%} | {forecast:.1%} |" for d,n,actual,forecast,_ in dec_report)
drivers="\n".join(f"| {idx} | {name} | {importance:.4f} |" for idx,(name,importance) in enumerate(perm[:15],1))
report=f"""# Historical holdout diagnostics (November 2023)

Model: {cfg['selected_model']}. Selection and training used months at/before October.
November was a **single held-out test**, not used to fit the model.
Observation unit: active customer in November, zero transactions in December target.

## Reliability by predicted risk decile
Ranked highest to lowest predicted risk. Compare mean predicted risk with observed
frequency; these are portfolio-style checks, **not evidence of production calibration**.

| Risk decile | Customers | Observed inactivity | Mean predicted probability |
|---|---:|---:|---:|
{cal_rows}

- Expected calibration error (10 equal-population bins): **{ece:.4f}**.
- Overall Brier score: {brier_score_loss(y,p):.4f} (lower is better).
- PR-AUC: {ap:.4f} (compared with holdout prevalence {np.mean(y):.4f}).
- Calibration improvement would require a separate dated calibration period;
  don't tune retrospectively on the final November test.

## Diagnostic feature influence (permutation, November sample)
Importance = decrease in average precision when one column is shuffled,
averaged over 2 repetitions on a seeded 8,000-row sample. Negative values
can arise from variance or correlated features.

| Rank | Feature | AP decrease |
|---|---|---:|
{drivers}

**Limitations:** Feature importance is predictive, not causal; correlated
transaction features can substitute for one another. This is diagnostic
after the model was frozen; do not retune the model using test results.

No customer-profile snapshots or demographics are included in this model.
"""
(R/"reports"/"model_diagnostics.md").write_text(report,encoding="utf-8")
print("DIAGNOSTICS_PASS holdout",len(y),"ece",round(ece,5),"drivers",perm[:5],flush=True)
