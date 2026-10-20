"""Reproducible local COFINFAD ETL with DuckDB, no raw-data mutations.

Inputs: data/raw/transactions_data.csv and customer_data.csv
Outputs: data/processed/customer_monthly.parquet, churn_features.parquet,
         dim_customer.parquet and reports/pipeline_validation.md

Run: python scripts/build_parquet_pipeline.py
"""
from pathlib import Path
from decimal import Decimal
import duckdb

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/"data"/"raw"
PROCESSED=ROOT/"data"/"processed"
REPORT=ROOT/"reports"/"pipeline_validation.md"
PROCESSED.mkdir(parents=True,exist_ok=True)
db=duckdb.connect(":memory:")
db.execute("SET threads=4")
tx_path=(RAW/"transactions_data.csv").as_posix().replace("'","''")
customer_path=(RAW/"customer_data.csv").as_posix().replace("'","''")
db.execute(f"""CREATE TEMP VIEW tx AS
SELECT CAST(customer_id AS VARCHAR) AS customer_id,
       CAST(date AS DATE) AS date,
       CAST(amount AS DECIMAL(38,2)) AS amount,
       CAST(type AS VARCHAR) AS type
FROM read_csv_auto('{tx_path}',header=true)""")
db.execute((ROOT/"src"/"features"/"customer_monthly_reference.sql").read_text(encoding="utf-8"))
db.execute((ROOT/"src"/"features"/"churn_features.sql").read_text(encoding="utf-8"))

# All transaction features are derived exclusively from raw transactions, never
# from customer_data, which includes vendor summaries and vendor churn_probability.
db.execute("""CREATE TEMP TABLE complete_features AS
SELECT * FROM expected_features""")
all_fields=[c[0] for c in db.execute("DESCRIBE complete_features").fetchall()]
monthly_fields=[
"customer_id","Month","CustomerStartMonth","TransactionCount","TotalAmount",
"AverageAmount","MaxAmount","TransferCount","PaymentCount","WithdrawalCount","DepositCount",
"TransferAmount","PaymentAmount","WithdrawalAmount","DepositAmount","FirstTransactionDate",
"LastTransactionDate","ActiveDays","WeekendTransactionCount","TransactionsPerCalendarDay",
"WeekendTransactionRatio","ObservedTenureMonths","PreferredTransactionType","PaymentShare",
"TransferShare","WithdrawalShare","DepositShare","InactiveMonth",
"PreviousTransactionCount","PreviousTotalAmount","PreviousPaymentCount",
"PreviousWithdrawalCount","PreviousDepositCount","PreviousTransferCount",
"TransactionCountChange","TransactionCountChangePct","TotalAmountChange","TotalAmountChangePct",
"ActivityDeclineFlag"]
missing_monthly=sorted(set(monthly_fields)-set(all_fields))
if missing_monthly: raise ValueError(f"Missing monthly stage fields: {missing_monthly}")

# Validate cardinality and raw reconciliations BEFORE publishing the output.
raw_count,raw_amount,raw_ids=db.execute(
"SELECT COUNT(*),SUM(amount),COUNT(DISTINCT customer_id) FROM tx").fetchone()
expected_count,expected_tx_sum,customer_count,zero_count,dupes=db.execute("""
SELECT COUNT(*),SUM(TransactionCount),
 COUNT(DISTINCT customer_id),
 COUNT(*) FILTER(WHERE TransactionCount=0),
 COUNT(*)-COUNT(DISTINCT (customer_id,Month))
FROM complete_features""").fetchone()
total_amount=db.execute("SELECT SUM(TotalAmount) FROM complete_features").fetchone()[0]
eligible,positives=db.execute("""SELECT
 COUNT(*) FILTER(WHERE EligibleForTraining=1),
 COUNT(*) FILTER(WHERE EligibleForTraining=1 AND InactiveNextMonth=1)
 FROM complete_features""").fetchone()
bad_target=db.execute("""SELECT COUNT(*) FROM complete_features
WHERE (EligibleForTraining=1 AND (TransactionCount=0 OR InactiveNextMonth IS NULL
OR Has6MonthHistory<>1 OR Month=DATE '2023-12-01'))
OR (Month=DATE '2023-12-01' AND InactiveNextMonth IS NOT NULL)
OR (TransactionCount=0 AND InactiveNextMonth IS NOT NULL)
""").fetchone()[0]
checks={
"transaction count": raw_count==expected_tx_sum,
"transaction amount": raw_amount==total_amount,
"customer identifiers": raw_ids==customer_count,
"customer-month keys unique": dupes==0,
"no leaked primary target": bad_target==0,
"expected 2023 snapshot row count": raw_count==3159157 and expected_count==569706,
"expected eligible rows": eligible==224360,
"expected positive labels": positives==39039,
}
if not all(checks.values()):
    raise AssertionError("ETL integrity gates failed: "+repr(checks))

# Customer dimension: only a deduplicated, key-validated snapshot. Transaction-
# derived vendor summaries are excluded, but sensitive/undated customer profile
# fields are RETAINED for descriptive analysis only, not historical ML training.
db.execute(f"""CREATE TEMP VIEW customer_raw AS
SELECT * FROM read_csv_auto('{customer_path}',header=true)""")
derived=[
"tx_count","avg_tx_value","total_tx_volume","first_tx","last_tx",
"monthly_transaction_count","average_transaction_value","total_transaction_volume",
"transaction_frequency","last_transaction_date","preferred_transaction_type",
"first_transaction_date","weekend_transaction_ratio","avg_daily_transactions",
"customer_tenure","churn_probability"
]
raw_columns=[c[0] for c in db.execute("DESCRIBE customer_raw").fetchall()]
to_drop=[col for col in derived if col in raw_columns]
remaining=[col for col in raw_columns if col not in (["customer_id"]+to_drop)]
q=lambda name:'"'+name.replace('"','""')+'"'
dim_select="CAST(customer_id AS VARCHAR) AS customer_id, "+", ".join(q(c) for c in remaining)
db.execute(f"CREATE TEMP TABLE dim_customer AS SELECT {dim_select} FROM customer_raw")
rows,distinct_ids,nulls=db.execute("""
SELECT COUNT(*), COUNT(DISTINCT customer_id),
COUNT(*) FILTER(WHERE customer_id IS NULL OR TRIM(customer_id)='')
FROM dim_customer""").fetchone()
unmatched=db.execute("""SELECT COUNT(*) FROM
 (SELECT DISTINCT customer_id FROM tx) t
 LEFT JOIN dim_customer d USING(customer_id)
 WHERE d.customer_id IS NULL""").fetchone()[0]
if rows!=distinct_ids or nulls or unmatched:
    raise AssertionError(f"Invalid customer dimension: rows={rows},ids={distinct_ids},missing={nulls},orphan={unmatched}")

# File writes are only reached after all quality gates pass.
def export(query,filename):
    dest=(PROCESSED/filename).as_posix().replace("'","''")
    db.execute(f"COPY ({query}) TO '{dest}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    print("WRITTEN",PROCESSED/filename)

export("SELECT "+", ".join(q(c) for c in monthly_fields)+" FROM complete_features","customer_monthly.parquet")
export("SELECT * FROM complete_features","churn_features.parquet")
export("SELECT * FROM dim_customer","dim_customer.parquet")

parquet_check={}
for f in ("customer_monthly.parquet","churn_features.parquet","dim_customer.parquet"):
    loc=(PROCESSED/f).as_posix().replace("'","''")
    actual=db.execute(f"SELECT COUNT(*) FROM read_parquet('{loc}')").fetchone()[0]
    target=rows if f.startswith("dim") else expected_count
    parquet_check[f]=(actual,target,actual==target)
if not all(v[2] for v in parquet_check.values()):
    raise AssertionError("Parquet write/readback validation failed")

summary="\n".join(f"| {name} | {'PASS' if ok else 'FAIL'} |" for name,ok in checks.items())
files="\n".join(f"| {fn} | {n:,} | {'PASS' if ok else 'FAIL'} |" for fn,(n,_,ok) in parquet_check.items())
REPORT.parent.mkdir(exist_ok=True)
REPORT.write_text(
f"""# Reproducible DuckDB / Parquet ETL validation

Built from original read-only COFINFAD raw CSVs using SQL located in
`src/features/`. The vetted 44-column behavioral semantics were independently
reconciled against the saved Power BI model before this migration.

| Metric | Value |
|---|---:|
| Raw transactions | {raw_count:,} |
| Unique transaction customers | {raw_ids:,} |
| Customer-month records | {expected_count:,} |
| Zero-transaction months | {zero_count:,} |
| Eligible records | {eligible:,} |
| Primary positive labels | {positives:,} |
| Dimension customer rows | {rows:,} |
| Dimension transaction orphans | {unmatched:,} |
| Feature columns in churn_features.parquet | {len(all_fields)} |
| Feature columns in customer_monthly.parquet | {len(monthly_fields)} |

## Gates
| Gate | Result |
|---|---|
{summary}

## Parquet readback
| File | Actual rows | Result |
|---|---:|---|
{files}

## Scope and privacy
- Raw CSVs and original PBIX were not altered by this script.
- Customer snapshots (app usage, satisfaction, NPS, product ownership, support,
  CLV etc.) are excluded from historical ML until a point-in-time source is proved.
- Do not use `churn_probability` as a feature or target.
- DimCustomer Parquet contains customer-level records and must remain private.
- Model label means next-month **transactional inactivity**, not account closure.
""",encoding="utf-8")
print("SUCCESS raw_count",raw_count,"months",expected_count,"eligible",eligible,"positives",positives,"features",len(all_fields))
print("REPORT",REPORT)
