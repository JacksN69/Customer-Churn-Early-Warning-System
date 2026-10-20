"""Audit customer_data at customer grain and transaction join coverage; raw is immutable."""
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[1]
CUSTOMERS = ROOT/"data"/"raw"/"customer_data.csv"
TRANSACTIONS = ROOT/"data"/"raw"/"transactions_data.csv"
REPORT = ROOT/"reports"/"dim_customer_quality.md"
db=duckdb.connect(":memory:")
customer_path=CUSTOMERS.as_posix().replace("'","''")
tx_path=TRANSACTIONS.as_posix().replace("'","''")
db.execute(f"CREATE VIEW customers AS SELECT * FROM read_csv_auto('{customer_path}',header=true,all_varchar=true)")
db.execute(f"CREATE VIEW tx_ids AS SELECT DISTINCT CAST(customer_id AS VARCHAR) AS customer_id FROM read_csv_auto('{tx_path}',header=true)")
cols=[c[0] for c in db.execute("DESCRIBE customers").fetchall()]
if "customer_id" not in cols: raise ValueError("Missing customer_id")
count,unique,missing=db.execute("""SELECT COUNT(*), COUNT(DISTINCT NULLIF(TRIM(customer_id),'')),
 COUNT(*) FILTER(WHERE NULLIF(TRIM(customer_id),'') IS NULL) FROM customers""").fetchone()
dups=db.execute("""SELECT COUNT(*) AS groups,COALESCE(SUM(n-1),0) AS extra
FROM(SELECT customer_id,COUNT(*) n FROM customers
 WHERE NULLIF(TRIM(customer_id),'') IS NOT NULL
 GROUP BY 1 HAVING COUNT(*)>1)""").fetchone()
conflicts=db.execute("""SELECT COUNT(*) FROM (
SELECT customer_id FROM (SELECT DISTINCT * FROM customers)
GROUP BY customer_id HAVING COUNT(*)>1
)""").fetchone()[0] if dups[0] else 0
# Ref joins use source customer IDs without silently picking one duplicate row.
joined=db.execute("""WITH ids AS (SELECT DISTINCT customer_id FROM customers)
SELECT
(SELECT COUNT(*) FROM tx_ids),
COUNT(*) FILTER(WHERE ids.customer_id IS NOT NULL)
FROM tx_ids t LEFT JOIN ids ON t.customer_id = ids.customer_id""").fetchone()
extra=db.execute("""SELECT COUNT(*) FROM(SELECT DISTINCT customer_id FROM customers) c
LEFT JOIN tx_ids t USING(customer_id)
WHERE t.customer_id IS NULL""").fetchone()[0]
type_errors={}
null_stats=[]
for c in cols:
    q='"'+c.replace('"','""')+'"'
    nonempty,blank,distinct=db.execute(f"""SELECT COUNT(*) FILTER(WHERE NULLIF(TRIM({q}),'') IS NOT NULL),
COUNT(*) FILTER(WHERE NULLIF(TRIM({q}),'') IS NULL),
COUNT(DISTINCT NULLIF(TRIM({q}),'')) FROM customers""").fetchone()
    null_stats.append((c,nonempty,blank,distinct))
age=(db.execute("""SELECT COUNT(*) FILTER(WHERE TRY_CAST(age AS INTEGER)<18 OR TRY_CAST(age AS INTEGER)>110),
COUNT(*) FILTER(WHERE TRY_CAST(age AS INTEGER) IS NULL AND NULLIF(TRIM(age),'') IS NOT NULL)
FROM customers""").fetchone() if "age" in cols else (None,None))
survey = (db.execute("""SELECT MIN(TRY_CAST(last_survey_date AS DATE)),
MAX(TRY_CAST(last_survey_date AS DATE)),
COUNT(*) FILTER(WHERE TRY_CAST(last_survey_date AS DATE)>DATE '2023-12-31')
FROM customers""").fetchone() if "last_survey_date" in cols else (None,None,None))
for name in ("age","household_size","satisfaction_score","nps_score","support_tickets_count","app_logins_frequency"):
    if name in cols:
        q='"'+name+'"'
        type_errors[name]=db.execute(f"SELECT COUNT(*) FROM customers WHERE NULLIF(TRIM({q}),'') IS NOT NULL AND TRY_CAST({q} AS DOUBLE) IS NULL").fetchone()[0]
# Track full scope of high-risk fields until snapshot date can be proven.
post_timing=[c for c in cols if c in {
"customer_segment","savings_account","credit_card","personal_loan","investment_account",
"insurance_product","active_products","app_logins_frequency","feature_usage_diversity",
"bill_payment_user","auto_savings_enabled","credit_utilization_ratio","international_transactions",
"failed_transactions","base_satisfaction","tx_satisfaction","product_satisfaction",
"satisfaction_score","nps_score","last_survey_date","support_tickets_count",
"resolved_tickets_ratio","app_store_rating","feedback_sentiment","feature_requests",
"complaint_topics","clv_segment","customer_lifetime_value"}]
derived=[c for c in cols if c in {
"tx_count","avg_tx_value","total_tx_volume","first_tx","last_tx",
"monthly_transaction_count","average_transaction_value","total_transaction_volume",
"transaction_frequency","last_transaction_date","preferred_transaction_type",
"first_transaction_date","weekend_transaction_ratio","avg_daily_transactions",
"customer_tenure","churn_probability"}]
null_rows="\n".join(f"| {c} | {n:,} | {b:,} ({b/count:.1%}) | {d:,} |" for c,n,b,d in null_stats)
type_rows="\n".join(f"| {c} | {v:,} |" for c,v in type_errors.items())
report=f"""# COFINFAD DimCustomer source quality audit

Raw CSV: `data/raw/customer_data.csv` (read only). Grain: expected one row per customer.

## Key quality / referential coverage

| Check | Value |
|---|---:|
| Customer source rows | {count:,} |
| Distinct nonblank customer IDs | {unique:,} |
| Blank/null customer IDs | {missing:,} |
| Duplicated customer-ID groups | {dups[0]:,} |
| Additional customer-ID rows | {dups[1]:,} |
| Duplicated IDs with nonidentical full rows | {conflicts:,} |
| Unique transaction customers | {joined[0]:,} |
| Transaction customer IDs matched to DimCustomer raw IDs | {joined[1]:,} |
| Transaction customer IDs missing in customer source | {joined[0]-joined[1]:,} |
| Customer IDs absent from transactions | {extra:,} |
| Source column count | {len(cols)} |

## Demographic and date checks
- Age outside [18,110]: {age[0]}
- Non-numeric nonblank ages: {age[1]}
- Earliest/latest observed survey dates: {survey[0]}, {survey[1]}
- Survey dates after Dec 2023: {survey[2]}
- A survey date column is **not** proof that the rest of the customer snapshot was known at observation month T.

## Numeric parsing

| Field | Nonblank invalid numeric strings |
|---|---:|
{type_rows}

## Column completeness and distinct counts

| Column | Populated | Missing/blank | Distinct |
|---|---:|---:|---:|
{null_rows}

## Feature policy
- Exclude all transaction-derived/customer-provider summary fields in DimCustomer ML: {', '.join(derived)}.
- Exclude vendor churn_probability from both target and ML features.
- Not historically defensible without dated source snapshots (do **not** use in historical training): {', '.join(post_timing)}.
- Treat age/profile attributes as potentially static descriptive data only; birth-date/collection timestamp must be established before using age or location in historical ML.
- Raw transaction activity remains the source of truth.

## Rules
- Never call `Table.Distinct` without profiling duplicate IDs and conflicts.
- Preserve customer raw data unchanged. Avoid exporting customer-level PII in this report.
"""
REPORT.write_text(report,encoding="utf-8")
print(f"CUSTOMER_ROWS={count}; UNIQUE={unique}; DUP_GROUPS={dups[0]}; CONFLICT_GROUPS={conflicts}; TX_CUSTOMER_MISSING={joined[0]-joined[1]}")
print(f"SURVEY_RANGE={survey}; INVALID_AGE={age}; COLUMNS={len(cols)}")
print(f"REPORT={REPORT}")
if missing or (joined[0]-joined[1]):raise SystemExit("Critical DimCustomer key issues")
