"""Independent COFINFAD customer-month reconciliation (read-only raw inputs).

This script reproduces the core monthly scaffold in DuckDB for validation.
It does NOT prove that a loaded Power BI CustomerMonthly table matches: compare
its exported monthly totals and customer-level rows separately.
"""
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "transactions_data.csv"
REPORT = ROOT / "reports" / "customer_monthly_reference.md"

if not RAW.exists():
    raise FileNotFoundError(RAW)

db = duckdb.connect(":memory:")
csv_path = RAW.as_posix().replace("'", "''")

# Match the current source data without editing raw files or removing duplicates.
db.execute(
    f"""
    CREATE TEMP VIEW tx AS
    SELECT CAST(customer_id AS VARCHAR) AS customer_id,
           CAST(date AS DATE) AS date,
           CAST(amount AS DECIMAL(38, 2)) AS amount,
           CAST(type AS VARCHAR) AS type
    FROM read_csv_auto('{csv_path}', header=true)
    """
)

raw = db.execute(
    """
    SELECT COUNT(*) AS n, COUNT(DISTINCT customer_id) AS customers,
           SUM(amount) AS amount,
           COUNT(*) FILTER (WHERE customer_id IS NULL OR date IS NULL) AS bad_keys
    FROM tx
    """
).fetchone()

if raw[3] != 0:
    raise ValueError(f"Raw data contains {raw[3]} null IDs/dates; aborting scaffold")

db.execute(
    """
    CREATE TEMP TABLE monthly_reference AS
    WITH actual AS (
        SELECT
            customer_id,
            DATE_TRUNC('month', date)::DATE AS Month,
            COUNT(*)::BIGINT AS TransactionCount,
            SUM(amount) AS TotalAmount,
            COUNT(*) FILTER (WHERE type = 'Transfer') AS TransferCount,
            COUNT(*) FILTER (WHERE type = 'Payment') AS PaymentCount,
            COUNT(*) FILTER (WHERE type = 'Withdrawal') AS WithdrawalCount,
            COUNT(*) FILTER (WHERE type = 'Deposit') AS DepositCount,
            SUM(CASE WHEN type = 'Transfer' THEN amount ELSE 0 END) AS TransferAmount,
            SUM(CASE WHEN type = 'Payment' THEN amount ELSE 0 END) AS PaymentAmount,
            SUM(CASE WHEN type = 'Withdrawal' THEN amount ELSE 0 END) AS WithdrawalAmount,
            SUM(CASE WHEN type = 'Deposit' THEN amount ELSE 0 END) AS DepositAmount
        FROM tx
        GROUP BY customer_id, Month
    ),
    starts AS (
        SELECT customer_id, MIN(Month) AS first_month
        FROM actual GROUP BY customer_id
    ),
    last_month AS (
        SELECT MAX(Month) AS final_month FROM actual
    ),
    scaffold AS (
        SELECT s.customer_id, g.Month::DATE AS Month
        FROM starts s
        CROSS JOIN last_month l
        CROSS JOIN LATERAL
          GENERATE_SERIES(s.first_month, l.final_month, INTERVAL '1 month') AS g(Month)
    )
    SELECT
        s.customer_id,
        s.Month,
        COALESCE(a.TransactionCount, 0)::BIGINT AS TransactionCount,
        COALESCE(a.TotalAmount, 0)::DECIMAL(38,2) AS TotalAmount,
        COALESCE(a.TransferCount, 0)::BIGINT AS TransferCount,
        COALESCE(a.PaymentCount, 0)::BIGINT AS PaymentCount,
        COALESCE(a.WithdrawalCount, 0)::BIGINT AS WithdrawalCount,
        COALESCE(a.DepositCount, 0)::BIGINT AS DepositCount,
        COALESCE(a.TransferAmount, 0)::DECIMAL(38,2) AS TransferAmount,
        COALESCE(a.PaymentAmount, 0)::DECIMAL(38,2) AS PaymentAmount,
        COALESCE(a.WithdrawalAmount, 0)::DECIMAL(38,2) AS WithdrawalAmount,
        COALESCE(a.DepositAmount, 0)::DECIMAL(38,2) AS DepositAmount
    FROM scaffold s
    LEFT JOIN actual a USING (customer_id, Month)
    """
)

result = db.execute(
    """
    SELECT
        COUNT(*) AS rows,
        COUNT(DISTINCT customer_id) AS customers,
        COUNT(*) FILTER (WHERE TransactionCount = 0) AS inactive_months,
        COUNT(*) FILTER (WHERE TransactionCount > 0) AS active_months,
        SUM(TransactionCount) AS tx_sum,
        SUM(TotalAmount) AS amount_sum,
        SUM(TransferCount+PaymentCount+WithdrawalCount+DepositCount) AS type_count_sum,
        SUM(TransferAmount+PaymentAmount+WithdrawalAmount+DepositAmount) AS type_amount_sum,
        COUNT(*) FILTER (WHERE
            TransactionCount <>
            TransferCount+PaymentCount+WithdrawalCount+DepositCount
        ) AS bad_type_counts,
        COUNT(*) FILTER (WHERE
            TotalAmount <>
            TransferAmount+PaymentAmount+WithdrawalAmount+DepositAmount
        ) AS bad_type_amounts
    FROM monthly_reference
    """
).fetchone()

duplicate_keys = db.execute(
    """
    SELECT COUNT(*) FROM (
        SELECT customer_id, Month
        FROM monthly_reference
        GROUP BY 1,2 HAVING COUNT(*) > 1
    )
    """
).fetchone()[0]

monthly = db.execute(
    """
    SELECT STRFTIME(Month, '%Y-%m') AS month,
           COUNT(*) AS customer_months,
           COUNT(*) FILTER (WHERE TransactionCount > 0) AS active,
           COUNT(*) FILTER (WHERE TransactionCount = 0) AS inactive,
           SUM(TransactionCount) AS transactions
    FROM monthly_reference
    GROUP BY Month ORDER BY Month
    """
).fetchall()

# Derive a reference target on a complete, ordered customer-month timeline.
# Has6MonthHistory means six observed months inclusive of T.
target_by_month = db.execute(
    """
    WITH ordered AS (
        SELECT customer_id, Month, TransactionCount,
               ROW_NUMBER() OVER (
                 PARTITION BY customer_id ORDER BY Month
               ) AS history_months,
               LEAD(TransactionCount) OVER (
                 PARTITION BY customer_id ORDER BY Month
               ) AS next_tx
        FROM monthly_reference
    )
    SELECT STRFTIME(Month, '%Y-%m') AS month,
           COUNT(*) AS eligible,
           COUNT(*) FILTER (WHERE next_tx = 0) AS positives,
           COUNT(*) FILTER (WHERE next_tx > 0) AS negatives
    FROM ordered
    WHERE history_months >= 6
      AND TransactionCount > 0
      AND next_tx IS NOT NULL
    GROUP BY Month ORDER BY Month
    """
).fetchall()

checks = {
    "customer counts reconcile": result[1] == raw[1],
    "transaction counts reconcile": result[4] == raw[0],
    "transaction amounts reconcile": result[5] == raw[2],
    "transaction-type counts reconcile": result[6] == result[4],
    "transaction-type amounts reconcile": result[7] == result[5],
    "no monthly type-count mismatches": result[8] == 0,
    "no monthly type-amount mismatches": result[9] == 0,
    "unique customer/month keys": duplicate_keys == 0,
    "scaffold partitions all rows": result[2] + result[3] == result[0],
}

checks_md = "\n".join(
    f"| {name} | {'PASS' if passed else 'FAIL'} |"
    for name, passed in checks.items()
)
monthly_md = "\n".join(
    f"| {m} | {total:,} | {active:,} | {inactive:,} | {tx:,} |"
    for m, total, active, inactive, tx in monthly
)
target_md = "\n".join(
    f"| {m} | {eligible:,} | {pos:,} | {neg:,} | "
    f"{(pos / eligible * 100) if eligible else 0:.2f}% |"
    for m, eligible, pos, neg in target_by_month
)
eligible_total = sum(row[1] for row in target_by_month)
positive_total = sum(row[2] for row in target_by_month)

REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(
    f"""# Independent Customer-Month Reference Audit

Generated from unmodified `data/raw/transactions_data.csv` in DuckDB.

**Important:** This is an independent reference; it does **not** establish
Power Query / PBIX equivalence until exported results are compared.

## Counts

| Metric | Value |
|---|---:|
| Raw transaction rows | {raw[0]:,} |
| Unique raw customers | {raw[1]:,} |
| Customer-month rows | {result[0]:,} |
| Active customer-months | {result[3]:,} |
| Zero-transaction customer-months | {result[2]:,} |
| Duplicate customer-month keys | {duplicate_keys:,} |
| Reference eligible rows | {eligible_total:,} |
| Reference positive labels | {positive_total:,} |
| Reference positive rate | {(positive_total / eligible_total * 100) if eligible_total else 0:.2f}% |

## Invariants

| Check | Result |
|---|---|
{checks_md}

## Monthly aggregation

| Month | Customer-months | Active | Inactive | Transactions |
|---|---:|---:|---:|---:|
{monthly_md}

## Reference labels: active at T, inactive at T+1

| Month T | Eligible | Positives | Negatives | Positive rate |
|---|---:|---:|---:|---:|
{target_md}

## Next validation gate

Compare against the actual Power BI `CustomerMonthly` and
`ChurnFeatures` results, first by month, then sampled customers and
eventually full row/key reconciliation.

Never treat this reference audit alone as proof that Power Query is correct.
Do not deduplicate matching raw transactions without source confirmation.
""",
    encoding="utf-8",
)
for name, passed in checks.items():
    print(("PASS" if passed else "FAIL") + ": " + name)
print(f"Reference customer-months: {result[0]:,}")
print(f"Eligible active T rows: {eligible_total:,}; positives: {positive_total:,}")
print(f"Report: {REPORT}")
if not all(checks.values()):
    raise SystemExit("Monthly reference validation FAILED; inspect report")
