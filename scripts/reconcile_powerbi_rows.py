"""Verify loaded Power BI customer-month features against an independent DuckDB rebuild.

Read-only source data and Power BI model. Compares every customer-month and
46 selected fields; records only mismatch totals in the Markdown report.
"""
import csv
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POWERBI = ROOT / "reports" / "powerbi_customer_month_actual.csv"
REPORT = ROOT / "reports" / "powerbi_duckdb_reconciliation.md"
if not POWERBI.exists():
    raise FileNotFoundError(POWERBI)

# Reuse the already validated raw DuckDB scaffold; it creates a temporary
# in-memory reference table, NOT new data sources or modified CSVs.
ns = runpy.run_path(str(ROOT / "scripts" / "validate_monthly_reference.py"))
db = ns["db"]

db.execute("""
CREATE TEMP TABLE expected_features AS
WITH extras AS (
    SELECT customer_id, DATE_TRUNC('month',date)::DATE AS Month,
           MIN(date) AS FirstTransactionDate,
           MAX(date) AS LastTransactionDate,
           COUNT(DISTINCT date) AS ActiveDays,
           COUNT(*) FILTER (WHERE ISODOW(date) IN (6,7)) AS WeekendTransactionCount
    FROM tx GROUP BY 1,2
),
base AS (
    SELECT m.*, e.FirstTransactionDate, e.LastTransactionDate,
           COALESCE(e.ActiveDays,0) AS ActiveDays,
           COALESCE(e.WeekendTransactionCount,0) AS WeekendTransactionCount
    FROM monthly_reference m LEFT JOIN extras e USING(customer_id,Month)
),
history AS (
    SELECT b.*,
           (ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY Month)-1) AS idx,
           MIN(Month) OVER (PARTITION BY customer_id) AS FirstObservedMonth,
           LAG(TransactionCount) OVER w AS PreviousTransactionCount,
           LAG(TotalAmount) OVER w AS PreviousTotalAmount,
           LEAD(TransactionCount,1) OVER w AS NextTx,
           LEAD(TransactionCount,2) OVER w AS Next2Tx,
           LEAD(TransactionCount,3) OVER w AS Next3Tx,
           SUM(TransactionCount) OVER (
             PARTITION BY customer_id ORDER BY Month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
           ) AS TransactionCount_Recent3M,
           SUM(TransactionCount) OVER (
             PARTITION BY customer_id ORDER BY Month ROWS BETWEEN 5 PRECEDING AND 3 PRECEDING
           ) AS raw_Previous3M,
           SUM(TotalAmount) OVER (
             PARTITION BY customer_id ORDER BY Month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
           ) AS TotalAmount_Recent3M,
           SUM(TotalAmount) OVER (
             PARTITION BY customer_id ORDER BY Month ROWS BETWEEN 5 PRECEDING AND 3 PRECEDING
           ) AS raw_PreviousAmount3M,
           MAX(LastTransactionDate) OVER (
             PARTITION BY customer_id ORDER BY Month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS KnownLastTx,
           MAX(CASE WHEN TransactionCount > 0
               THEN ROW_NUMBER_PLACEHOLDER ELSE NULL END) OVER (
             PARTITION BY customer_id ORDER BY Month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS placeholder
    FROM base b
    WINDOW w AS (PARTITION BY customer_id ORDER BY Month)
),
with_streak AS (
    SELECT h.* EXCLUDE (placeholder),
           MAX(CASE WHEN TransactionCount > 0 THEN idx ELSE NULL END)
             OVER (PARTITION BY customer_id ORDER BY Month
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS LastActiveIdx
    FROM history h
),
measures AS (
    SELECT s.*,
           CASE WHEN idx >= 5 THEN raw_Previous3M ELSE NULL END AS TransactionCount_Previous3M,
           CASE WHEN idx >= 5 THEN raw_PreviousAmount3M ELSE NULL END AS TotalAmount_Previous3M,
           CASE WHEN PreviousTransactionCount IS NULL THEN NULL
             ELSE TransactionCount - PreviousTransactionCount END AS TransactionCountChange,
           CASE WHEN PreviousTotalAmount IS NULL THEN NULL
             ELSE TotalAmount - PreviousTotalAmount END AS TotalAmountChange,
           CASE WHEN PreviousTransactionCount IS NULL THEN NULL
             WHEN PreviousTransactionCount = 0 AND TransactionCount = 0 THEN 0
             WHEN PreviousTransactionCount = 0 THEN NULL
             ELSE (TransactionCount - PreviousTransactionCount)::DOUBLE / PreviousTransactionCount END
             AS TransactionCountChangePct,
           CASE WHEN PreviousTotalAmount IS NULL THEN NULL
             WHEN PreviousTotalAmount = 0 AND TotalAmount = 0 THEN 0
             WHEN PreviousTotalAmount = 0 THEN NULL
             ELSE (TotalAmount - PreviousTotalAmount)::DOUBLE / PreviousTotalAmount END
             AS TotalAmountChangePct,
           CASE WHEN idx < 5 THEN NULL
             WHEN raw_Previous3M = 0 AND TransactionCount_Recent3M = 0 THEN 0
             WHEN raw_Previous3M = 0 THEN NULL
             ELSE (TransactionCount_Recent3M-raw_Previous3M)::DOUBLE/raw_Previous3M END
             AS TransactionCount_3M_ChangePct,
           CASE WHEN idx < 5 THEN NULL
             WHEN raw_PreviousAmount3M = 0 AND TotalAmount_Recent3M = 0 THEN 0
             WHEN raw_PreviousAmount3M = 0 THEN NULL
             ELSE (TotalAmount_Recent3M-raw_PreviousAmount3M)::DOUBLE/raw_PreviousAmount3M END
             AS TotalAmount_3M_ChangePct
    FROM with_streak s
)
SELECT
  customer_id, Month, TransactionCount, TotalAmount,
  TransferCount,PaymentCount,WithdrawalCount,DepositCount,
  TransferAmount,PaymentAmount,WithdrawalAmount,DepositAmount,
  FirstTransactionDate,LastTransactionDate,ActiveDays,WeekendTransactionCount,
  TransactionCount::DOUBLE / DATE_DIFF('day', Month, Month + INTERVAL '1 month')
    AS TransactionsPerCalendarDay,
  CASE WHEN TransactionCount = 0 THEN 0 ELSE WeekendTransactionCount::DOUBLE / TransactionCount END
    AS WeekendTransactionRatio,
  DATE_DIFF('month',FirstObservedMonth, Month) AS ObservedTenureMonths,
  CASE WHEN TransactionCount = 0 THEN NULL
       WHEN TransferCount = GREATEST(TransferCount,PaymentCount,WithdrawalCount,DepositCount) THEN 'Transfer'
       WHEN PaymentCount = GREATEST(TransferCount,PaymentCount,WithdrawalCount,DepositCount) THEN 'Payment'
       WHEN WithdrawalCount = GREATEST(TransferCount,PaymentCount,WithdrawalCount,DepositCount) THEN 'Withdrawal'
       ELSE 'Deposit' END AS PreferredTransactionType,
  CASE WHEN TransactionCount=0 THEN 0 ELSE PaymentCount::DOUBLE/TransactionCount END AS PaymentShare,
  CASE WHEN TransactionCount=0 THEN 0 ELSE TransferCount::DOUBLE/TransactionCount END AS TransferShare,
  CASE WHEN TransactionCount=0 THEN 0 ELSE WithdrawalCount::DOUBLE/TransactionCount END AS WithdrawalShare,
  CASE WHEN TransactionCount=0 THEN 0 ELSE DepositCount::DOUBLE/TransactionCount END AS DepositShare,
  CASE WHEN TransactionCount=0 THEN 1 ELSE 0 END AS InactiveMonth,
  PreviousTransactionCount, PreviousTotalAmount, TransactionCountChange, TransactionCountChangePct,
  TotalAmountChange, TotalAmountChangePct,
  CASE WHEN TransactionCountChangePct <= -.5 THEN 1 ELSE 0 END AS ActivityDeclineFlag,
  CASE WHEN TransactionCount=0 THEN idx-COALESCE(LastActiveIdx,-1) ELSE 0 END
    AS ConsecutiveInactiveMonths,
  DATE_DIFF('day',KnownLastTx,LAST_DAY(Month)) AS DaysSinceLastTransaction,
  TransactionCount_Recent3M, TransactionCount_Previous3M, TransactionCount_3M_ChangePct,
  TotalAmount_Recent3M, TotalAmount_Previous3M, TotalAmount_3M_ChangePct,
  CASE WHEN TransactionCount_3M_ChangePct <= -.5 THEN 1 ELSE 0 END AS TransactionDecline50Pct,
  CASE WHEN TotalAmount_3M_ChangePct <= -.5 THEN 1 ELSE 0 END AS SpendingDecline50Pct,
  CASE WHEN NextTx IS NULL OR TransactionCount=0 THEN NULL
       WHEN NextTx=0 THEN 1 ELSE 0 END AS InactiveNextMonth,
  CASE WHEN Next3Tx IS NULL OR TransactionCount=0 THEN NULL
       WHEN NextTx+Next2Tx+Next3Tx=0 THEN 1 ELSE 0 END AS ExtendedInactivityNext3Months,
  CASE WHEN idx >= 5 THEN 1 ELSE 0 END AS Has6MonthHistory,
  CASE WHEN idx >= 5 AND TransactionCount>0 AND NextTx IS NOT NULL THEN 1 ELSE 0 END
    AS EligibleForTraining
FROM measures
""".replace(
    """           MAX(CASE WHEN TransactionCount > 0
               THEN ROW_NUMBER_PLACEHOLDER ELSE NULL END) OVER (
             PARTITION BY customer_id ORDER BY Month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS placeholder""",
    """           0 AS placeholder"""
))

# Load the exact values returned by the Power BI data engine.
pbi_path = POWERBI.as_posix().replace("'", "''")
db.execute(f"CREATE TEMP VIEW raw_model_rows AS SELECT * FROM read_csv_auto('{pbi_path}', header=true, sample_size=-1)")
original_columns = [item[0] for item in db.execute("DESCRIBE SELECT * FROM raw_model_rows").fetchall()]
def normalize(name):
    return name.rsplit("[", 1)[-1].rstrip("]") if "[" in name else name

cols = [normalize(c) for c in original_columns]
if len(cols) != len(set(cols)):
    raise ValueError("Duplicate normalized column names in Power BI extract")
expressions = []
for orig, clean in zip(original_columns,cols):
    ident = '"' + orig.replace('"','""') + '"'
    alias = '"' + clean.replace('"','""') + '"'
    if clean == "Month" or clean.endswith("Date"):
        expressions.append(f"TRY_CAST({ident} AS DATE) AS {alias}")
    elif clean == "customer_id" or clean == "PreferredTransactionType":
        expressions.append(f"CAST({ident} AS VARCHAR) AS {alias}")
    else:
        expressions.append(f"{ident} AS {alias}")
db.execute(f"CREATE TEMP TABLE model_rows AS SELECT {', '.join(expressions)} FROM raw_model_rows")

expected_columns = {item[0] for item in db.execute("DESCRIBE expected_features").fetchall()}
missing_cols = sorted(set(cols)-expected_columns)
if missing_cols:
    raise ValueError(f"Expected reference missing columns: {missing_cols}")

stats = db.execute("""
SELECT
 (SELECT COUNT(*) FROM model_rows) AS actual_rows,
 (SELECT COUNT(*) FROM expected_features) AS expected_rows,
 (SELECT COUNT(*) FROM model_rows WHERE customer_id IS NULL OR Month IS NULL) AS bad_model_keys,
 (SELECT COUNT(*) FROM (SELECT customer_id,Month FROM model_rows GROUP BY 1,2 HAVING COUNT(*)>1))
     AS model_duplicate_keys,
 (SELECT COUNT(*) FROM model_rows p LEFT JOIN expected_features e USING(customer_id,Month)
     WHERE e.customer_id IS NULL) AS unexpected_rows,
 (SELECT COUNT(*) FROM expected_features e LEFT JOIN model_rows p USING(customer_id,Month)
     WHERE p.customer_id IS NULL) AS missing_rows
""").fetchone()

numeric_float_columns = {
    "TransactionsPerCalendarDay","WeekendTransactionRatio",
    "PaymentShare","TransferShare","WithdrawalShare","DepositShare",
    "TransactionCountChangePct","TotalAmountChangePct",
    "TransactionCount_3M_ChangePct","TotalAmount_3M_ChangePct"
}
# DuckDB IS DISTINCT FROM respects paired nulls; approximate tolerance for binary float features.
results = []
for col in cols:
    if col in ("customer_id","Month"):
        continue
    name = '"' + col.replace('"','""') + '"'
    if col in numeric_float_columns:
        difference = f"""(
          ((p.{name} IS NULL) <> (e.{name} IS NULL)) OR
          (p.{name} IS NOT NULL AND e.{name} IS NOT NULL AND
           ABS(CAST(p.{name} AS DOUBLE) - CAST(e.{name} AS DOUBLE)) > 0.00000001)
        )"""
    elif col in {"TotalAmount","TransferAmount","PaymentAmount","WithdrawalAmount",
                 "DepositAmount","PreviousTotalAmount","TotalAmountChange",
                 "TotalAmount_Recent3M","TotalAmount_Previous3M"}:
        difference = f"""(
          ((p.{name} IS NULL) <> (e.{name} IS NULL)) OR
          (p.{name} IS NOT NULL AND e.{name} IS NOT NULL AND
          ABS(CAST(p.{name} AS DOUBLE)-CAST(e.{name} AS DOUBLE)) > 0.01)
        )"""
    else:
        difference = f"p.{name} IS DISTINCT FROM e.{name}"
    mismatches = db.execute(
        f"""SELECT COUNT(*) FROM model_rows p JOIN expected_features e
            USING(customer_id,Month) WHERE {difference}"""
    ).fetchone()[0]
    results.append((col,mismatches))
    if mismatches:
        print(f"MISMATCH {col}: {mismatches:,}")
    else:
        print(f"PASS {col}")

failed_fields = sum(1 for _,n in results if n)
full_pass = (stats[0]==stats[1] and all(n==0 for n in stats[2:]) and failed_fields==0)
rows = "\n".join(f"| {n} | {m:,} | {'PASS' if m==0 else 'FAIL'} |" for n,m in results)
REPORT.write_text(f"""# Power BI ↔ DuckDB customer-month reconciliation

## Method

Direct DAX export from the open saved Power BI Desktop model (`ChurnFeatures`)
was joined by (`customer_id`, `Month`) to an independent DuckDB build from
the unmodified raw CSV. This is a *saved-model* comparison, not a source refresh.
All {len(results)} non-key columns below were evaluated for every matched row.
Amounts tolerate up to 0.01; percentage/rate floats up to 1e-8; other values exact.

| Metric | Value |
|---|---:|
| Power BI rows | {stats[0]:,} |
| DuckDB rows | {stats[1]:,} |
| Invalid Power BI keys | {stats[2]:,} |
| Duplicate Power BI keys | {stats[3]:,} |
| Unexpected Power BI keys | {stats[4]:,} |
| Missing Power BI keys | {stats[5]:,} |
| Fields with discrepancies | {failed_fields:,} / {len(results)} |

## Per-field comparison

| Field | Mismatched rows | Result |
|---|---:|---|
{rows}

## Verdict

**{'PASS — exact key population and all selected fields reconcile' if full_pass else 'FAIL — investigate differences before declaring feature parity'}**

Notes:
- This audit compares the existing loaded/saved PBIX model with the raw CSVs.
- It does not prove that a future Power BI refresh will use the same CSV file.
- Snapshot export `reports/powerbi_customer_month_actual.csv` contains
  customer IDs and must not be published to GitHub.
- Unknown point-in-time provenance of customer profile fields is not resolved
  by this behavioral parity audit.
""",encoding="utf-8")
print(f"FULL_PARITY={full_pass}; PowerBI rows={stats[0]:,}; DuckDB rows={stats[1]:,}")
print(f"Report: {REPORT}")
if not full_pass:
    raise SystemExit(1)
