"""Build and execute notebooks/01_eda.ipynb (Phase 11 EDA).

Run: python notebooks/build_eda_notebook.py
The notebook is executed so its outputs (tables and charts) are stored in the file.
Only aggregates are displayed; no customer-level rows are printed.
"""
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

NB_PATH = Path(__file__).resolve().parent / "01_eda.ipynb"

cells = []
md = lambda s: cells.append(new_markdown_cell(s))
code = lambda s: cells.append(new_code_cell(s))

md("""# Exploratory analysis: next-month transactional inactivity

**Target:** `InactiveNextMonth` = active in month T and zero transactions in T+1.
This is a *transactional inactivity proxy*, not confirmed account closure.
All comparisons are descriptive associations on labelled customer-month rows (T = Jun-Nov 2023);
they do not imply causation. Customer-profile cuts use the undated `DimCustomer` snapshot for
segmentation only, never as model input.""")

code("""
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import duckdb, numpy as np, pandas as pd
import matplotlib.pyplot as plt
plt.rcParams.update({"figure.figsize": (9, 4), "axes.grid": True, "axes.spines.top": False, "axes.spines.right": False})
pd.set_option("display.width", 200, "display.max_columns", 30)

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "src").exists())
P = ROOT / "data" / "processed"
db = duckdb.connect()
db.execute(f"CREATE VIEW cf AS SELECT * FROM read_parquet('{(P / 'churn_features.parquet').as_posix()}')")
db.execute(f"CREATE VIEW dim AS SELECT * FROM read_parquet('{(P / 'dim_customer.parquet').as_posix()}')")
lab = db.execute(\"\"\"SELECT f.*, strftime(Month,'%Y-%m') AS period FROM cf f WHERE EligibleForTraining = 1\"\"\").fetchdf()
lab["y"] = lab["InactiveNextMonth"].astype(int)
print(f"{len(lab):,} labelled customer-month rows; {lab.customer_id.nunique():,} customers; positive rate {lab.y.mean():.2%}")
""")

md("## 1. Target distribution (overall and by month)")
code("""
by_month = lab.groupby("period").y.agg(rows="size", inactive="sum", rate="mean")
by_month["rate"] = (by_month["rate"] * 100).round(2)
display(pd.DataFrame({"overall": [len(lab), int(lab.y.sum()), round(lab.y.mean() * 100, 2)]}, index=["rows", "inactive_next_month=1", "rate %"]).T)
display(by_month)
ax = by_month["rate"].plot(kind="bar", color="#4C78A8"); ax.set_ylabel("% inactive next month"); ax.set_title("Target rate by observation month"); plt.show()
print("Range across months: %.2f%% - %.2f%%" % (by_month.rate.min(), by_month.rate.max()))
""")

md("### Are inactive-next-month customers really gone? (transient gaps)")
code("""
gap = db.execute(\"\"\"
WITH t AS (SELECT customer_id, Month, TransactionCount tc, InactiveNextMonth y,
           lead(TransactionCount,2) OVER (PARTITION BY customer_id ORDER BY Month) n2,
           ExtendedInactivityNext3Months e FROM cf)
SELECT COUNT(*) FILTER (WHERE y=1) AS inactive_next_month,
       COUNT(*) FILTER (WHERE y=1 AND n2>0) AS active_again_at_T_plus_2,
       ROUND(100.0*COUNT(*) FILTER (WHERE y=1 AND n2>0)/NULLIF(COUNT(*) FILTER (WHERE y=1 AND n2 IS NOT NULL),0),1) AS pct_return_T_plus_2,
       COUNT(*) FILTER (WHERE e=1) AS extended_inactivity_3m, COUNT(*) FILTER (WHERE e IS NOT NULL) AS extended_observed
FROM t\"\"\").fetchdf()
display(gap)
""")

md("## 2. Behavioural deterioration: inactive-next-month vs active-next-month")
code("""
cols = ["TransactionCount", "TotalAmount", "ActiveDays", "DaysSinceLastTransaction",
        "TransactionCountChangePct", "TotalAmountChangePct",
        "TransactionCount_3M_ChangePct", "TotalAmount_3M_ChangePct"]
rows = []
for c in cols:
    a, b = lab.loc[lab.y == 0, c].astype(float), lab.loc[lab.y == 1, c].astype(float)
    pooled = np.sqrt((a.var() + b.var()) / 2)
    rows.append({"feature": c, "median_active_next": a.median(), "median_inactive_next": b.median(),
                 "mean_active_next": a.mean(), "mean_inactive_next": b.mean(),
                 "std_diff": (b.mean() - a.mean()) / pooled if pooled else np.nan,
                 "null_rate_%": round(lab[c].isna().mean() * 100, 2)})
cmp = pd.DataFrame(rows).set_index("feature")
display(cmp.round(3))
fig, axes = plt.subplots(2, 4, figsize=(15, 6))
for ax, c in zip(axes.ravel(), cols):
    data = [lab.loc[lab.y == v, c].dropna().clip(lab[c].quantile(.01), lab[c].quantile(.99)) for v in (0, 1)]
    ax.boxplot(data, tick_labels=["active next", "inactive next"], showfliers=False); ax.set_title(c, fontsize=9)
plt.tight_layout(); plt.show()
""")

md("### Monthly trend before the event: average TransactionCount by months-to-inactivity")
code("""
trend = db.execute(\"\"\"
WITH ev AS (SELECT customer_id, Month AS event_month FROM cf WHERE EligibleForTraining=1 AND InactiveNextMonth=1),
base AS (SELECT customer_id, Month AS event_month FROM cf WHERE EligibleForTraining=1 AND InactiveNextMonth=0)
SELECT 'inactive next month' AS grp, date_diff('month', e.event_month, f.Month) AS rel_month, AVG(f.TransactionCount) AS avg_tx
FROM ev e JOIN cf f ON f.customer_id=e.customer_id AND date_diff('month', e.event_month, f.Month) BETWEEN -5 AND 0 GROUP BY 1,2
UNION ALL
SELECT 'active next month', date_diff('month', e.event_month, f.Month), AVG(f.TransactionCount)
FROM base e JOIN cf f ON f.customer_id=e.customer_id AND date_diff('month', e.event_month, f.Month) BETWEEN -5 AND 0 GROUP BY 1,2
\"\"\").fetchdf().pivot(index="rel_month", columns="grp", values="avg_tx")
display(trend.round(2)); trend.plot(marker="o", title="Average monthly TransactionCount in the 6 months up to T"); plt.xlabel("months relative to T"); plt.show()
""")

md("## 3. Transaction composition")
code("""
shares = ["PaymentShare", "TransferShare", "WithdrawalShare", "DepositShare"]
comp = lab.groupby("y")[shares].mean().T; comp.columns = ["active next", "inactive next"]
comp["diff (pp)"] = ((comp["inactive next"] - comp["active next"]) * 100).round(2)
display(comp.round(4))
comp[["active next", "inactive next"]].plot(kind="bar", title="Mean transaction-type share in month T"); plt.show()
pref = lab.groupby("PreferredTransactionType").y.agg(rows="size", rate="mean"); pref["rate"] = (pref.rate * 100).round(2); display(pref)
""")

md("## 4. Recency: DaysSinceLastTransaction vs next-month inactivity")
code("""
bins = [-1, 0, 3, 7, 14, 21, 31, 60, 400]
lab["recency_bin"] = pd.cut(lab.DaysSinceLastTransaction, bins=bins)
rec = lab.groupby("recency_bin", observed=True).y.agg(rows="size", rate="mean"); rec["rate_%"] = (rec.pop("rate") * 100).round(2)
display(rec)
ax = rec["rate_%"].plot(marker="o", title="Inactive-next-month rate by days since last transaction (end of T)")
ax.set_xticks(range(len(rec))); ax.set_xticklabels([str(i) for i in rec.index], rotation=30); ax.set_ylabel("%"); plt.show()
""")

md("## 5. Customer characteristics (segmentation only, no causal claim)")
code("""
seg = lab.merge(db.execute("SELECT customer_id, age, gender, location, income_bracket, acquisition_channel, education_level, occupation FROM dim").fetchdf(), on="customer_id", how="left")
overall = seg.y.mean()
for col in ["age", "income_bracket", "acquisition_channel", "education_level", "gender", "location", "occupation"]:
    t = seg.groupby(col).agg(rows=("y", "size"), customers=("customer_id", "nunique"), rate=("y", "mean"))
    t = t[t.rows >= 500]; t["rate_%"] = (t.pop("rate") * 100).round(2); t["vs_overall_pp"] = (t["rate_%"] - overall * 100).round(2)
    print(f"--- {col}  (overall {overall:.2%}; groups with >=500 customer-months; spread {t['rate_%'].max() - t['rate_%'].min():.2f} pp)")
    display(t.sort_values("rate_%", ascending=False).head(12))
""")

md("## 6. Why `ObservedTenureMonths` is excluded from the model")
code("""
chk = db.execute(\"\"\"SELECT strftime(Month,'%Y-%m') AS month, MIN(ObservedTenureMonths) mn, MAX(ObservedTenureMonths) mx,
 ROUND(100.0*COUNT(*) FILTER (WHERE ObservedTenureMonths=date_diff('month',DATE '2023-01-01',Month))/COUNT(*),1) AS pct_equal_calendar_index
 FROM cf WHERE EligibleForTraining=1 OR (Month=DATE '2023-12-01' AND TransactionCount>0 AND Has6MonthHistory=1) GROUP BY 1 ORDER BY 1\"\"\").fetchdf()
display(chk)
print("~80% of customers first appear in Jan 2023 (left-censored window), so tenure is mostly the month index; "
      "test/scoring months contain tenure values never seen in training.")
""")

md("""## Summary of findings
(See `reports/eda_summary.md` for the written summary derived from these tables.)""")

nb = new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}})
NotebookClient(nb, timeout=900, kernel_name="python3", resources={"metadata": {"path": str(NB_PATH.parent)}}).execute()
nbformat.write(nb, NB_PATH)
print("written", NB_PATH)
