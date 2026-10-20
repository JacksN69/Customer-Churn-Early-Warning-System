"""Audit missingness, credit-card association, and available field timestamps.

Does not modify raw sources.
"""
from pathlib import Path
import duckdb, json, importlib.util, csv
R=Path(__file__).resolve().parents[1]
con=duckdb.connect()
raw=(R/"data/raw/customer_data.csv").as_posix().replace("'","''")
con.execute(f"CREATE VIEW c AS SELECT * FROM read_csv_auto('{raw}',header=true)")
schema=con.execute("DESCRIBE c").fetchall()
cols=[x[0] for x in schema]
print("DEPENDENCIES:", {x:bool(importlib.util.find_spec(x)) for x in ["duckdb","sklearn","numpy","pandas","pyarrow","matplotlib","xgboost","lightgbm"]},flush=True)
print("COLUMNS:",cols,flush=True)
stats=con.execute("""
SELECT credit_card,
       COUNT(*) AS n_rows,
       COUNT(*) FILTER (WHERE credit_utilization_ratio IS NULL) missing_util,
       COUNT(*) FILTER (WHERE credit_utilization_ratio IS NOT NULL) recorded_util,
       COUNT(*) FILTER (WHERE feature_requests IS NULL OR TRIM(feature_requests)='') no_requests,
       COUNT(*) FILTER (WHERE complaint_topics IS NULL OR TRIM(complaint_topics)='') no_topics
FROM c GROUP BY credit_card ORDER BY credit_card
""").fetchall()
print("CREDIT_MISSINGNESS_BY_CARD:",stats,flush=True)
missing=con.execute("""
SELECT
  COUNT(*) FILTER(WHERE credit_utilization_ratio IS NULL),
  COUNT(*) FILTER(WHERE feature_requests IS NULL OR TRIM(feature_requests)=''),
  COUNT(*) FILTER(WHERE complaint_topics IS NULL OR TRIM(complaint_topics)=''),
  COUNT(*) FILTER(WHERE credit_card=FALSE AND credit_utilization_ratio IS NOT NULL),
  COUNT(*) FILTER(WHERE credit_card=TRUE AND credit_utilization_ratio IS NULL),
  MIN(last_survey_date),MAX(last_survey_date),
  COUNT(DISTINCT last_survey_date)
FROM c""").fetchone()
print("SUMMARY:",missing,flush=True)
print("SURVEY_DISTRIBUTION:")
for row in con.execute("""
SELECT DATE_TRUNC('month',last_survey_date)::DATE AS month, COUNT(*)
FROM c GROUP BY 1 ORDER BY 1""").fetchall():print(row,flush=True)
print("OTHER_DATETIME_COLUMNS:",[x for x in cols if any(v in x.lower() for v in ["date","time","timestamp","_at","first_","last_"])],flush=True)
print("CANDIDATE_DOCUMENTS:")
for f in R.rglob("*"):
    if f.is_file() and (f.suffix.lower() in {".md",".json",".yaml",".yml",".pdf",".txt",".csv"}):
        if "data" not in f.parts and "reports" not in f.parts and "powerquery" not in f.parts and ".venv" not in f.parts:
            print(f.relative_to(R),flush=True)
report=f"""# Profile missingness and historical timing audit

Source: original `customer_data.csv` with {sum(v[1] for v in stats):,} customer records.

| Check | Count |
|---|---:|
| Credit ratio blank/null | {missing[0]:,} |
| Requests blank/null | {missing[1]:,} |
| Complaint topics blank/null | {missing[2]:,} |
| Credit card = FALSE but ratio present | {missing[3]:,} |
| Credit card = TRUE but ratio missing | {missing[4]:,} |

| Credit card | Customers | Ratio missing | Ratio present |
|---|---:|---:|---:|
"""+ "\n".join(f"| {card} | {n:,} | {m:,} | {present:,} |" for card,n,m,present,*_ in stats)+ f"""

## Missing-value interpretation

- Credit utilization ratio is **not applicable** if there is no credit card;
  its numeric value must remain NULL, **not 0**.
- Blank `feature_requests` and `complaint_topics` mean **Not recorded**,
  not confirmed none/zero. Raw NULLs are preserved.
- Power BI should display separate category labels while numeric analyses
  continue to exclude missing utilization from the denominator.

## Historical feature availability

- Raw `transactions_data.csv` has transaction dates; transaction-derived
  features use data through the end of observation month T.
- `customer_data.csv` is one undated snapshot per customer. It contains
  `last_survey_date`, spanning {missing[5]}–{missing[6]} across {missing[7]} distinct days.
  This may date a last survey, but it does not timestamp product ownership,
  app usage, support metrics, credit utilization, or the entire satisfaction
  record. It does not establish as-of snapshots for arbitrary months.
- Vendor/transaction summary fields in customer data (first_tx/last_tx etc.)
  do not establish acquisition timestamps for other fields.
- Hence none of these snapshot fields can be defensibly backfilled to
  month T; keep them out of historical training. No imputed recording dates.
"""
(R/"reports/profile_missingness_temporal_audit.md").write_text(report,encoding="utf-8")
print("REPORT_WRITTEN",flush=True)
