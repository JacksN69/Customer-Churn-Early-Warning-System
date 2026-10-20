from pathlib import Path
import duckdb


# ============================================================
# Paths
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CSV_PATH = PROJECT_ROOT / "data" / "raw" / "transactions_data.csv"
REPORT_PATH = PROJECT_ROOT / "reports" / "data_quality_raw.md"


if not CSV_PATH.exists():
    raise FileNotFoundError(
        f"Could not find transaction file at:\n{CSV_PATH}"
    )


# DuckDB SQL-safe path
csv_sql_path = CSV_PATH.as_posix().replace("'", "''")


# ============================================================
# Connect to DuckDB
# ============================================================

con = duckdb.connect()


# ============================================================
# Create a view over the CSV
#
# The CSV remains unchanged.
# DuckDB reads it directly.
# ============================================================

con.execute(
    f"""
    CREATE OR REPLACE VIEW transactions AS
    SELECT *
    FROM read_csv_auto(
        '{csv_sql_path}',
        header = true
    );
    """
)


# ============================================================
# 1. General dataset summary
# ============================================================

summary = con.execute(
    """
    SELECT
        COUNT(*) AS row_count,
        COUNT(DISTINCT customer_id) AS unique_customers,
        MIN(date) AS min_date,
        MAX(date) AS max_date,

        SUM(CASE WHEN customer_id IS NULL THEN 1 ELSE 0 END)
            AS null_customer_ids,

        SUM(CASE WHEN date IS NULL THEN 1 ELSE 0 END)
            AS null_dates,

        SUM(CASE WHEN amount IS NULL THEN 1 ELSE 0 END)
            AS null_amounts,

        SUM(CASE WHEN type IS NULL THEN 1 ELSE 0 END)
            AS null_types

    FROM transactions;
    """
).fetchone()


(
    row_count,
    unique_customers,
    min_date,
    max_date,
    null_customer_ids,
    null_dates,
    null_amounts,
    null_types,
) = summary


# ============================================================
# 2. Transaction types
# ============================================================

transaction_types = con.execute(
    """
    SELECT
        type,
        COUNT(*) AS count
    FROM transactions
    GROUP BY type
    ORDER BY count DESC;
    """
).fetchall()


# ============================================================
# 3. Invalid/unexpected transaction types
# ============================================================

invalid_types = con.execute(
    """
    SELECT
        type,
        COUNT(*) AS count
    FROM transactions
    WHERE type IS NOT NULL
      AND type NOT IN (
          'Transfer',
          'Payment',
          'Withdrawal',
          'Deposit'
      )
    GROUP BY type
    ORDER BY count DESC;
    """
).fetchall()


# ============================================================
# 4. Amount validation
# ============================================================

amount_stats = con.execute(
    """
    SELECT
        MIN(amount) AS min_amount,
        MAX(amount) AS max_amount,
        AVG(amount) AS avg_amount,

        SUM(CASE WHEN amount < 0 THEN 1 ELSE 0 END)
            AS negative_amounts,

        SUM(CASE WHEN amount = 0 THEN 1 ELSE 0 END)
            AS zero_amounts,

        SUM(CASE WHEN amount <= 0 THEN 1 ELSE 0 END)
            AS non_positive_amounts

    FROM transactions;
    """
).fetchone()


(
    min_amount,
    max_amount,
    avg_amount,
    negative_amounts,
    zero_amounts,
    non_positive_amounts,
) = amount_stats


# ============================================================
# 5. Exact duplicate rows
#
# "Duplicate" here means all four fields are identical:
#
# customer_id + date + amount + type
#
# This does NOT automatically prove the transaction is invalid,
# because the source has no unique transaction ID.
# ============================================================

duplicate_stats = con.execute(
    """
    WITH duplicate_groups AS (
        SELECT
            customer_id,
            date,
            amount,
            type,
            COUNT(*) AS n
        FROM transactions
        GROUP BY
            customer_id,
            date,
            amount,
            type
        HAVING COUNT(*) > 1
    )

    SELECT
        COUNT(*) AS duplicate_groups,
        COALESCE(SUM(n - 1), 0) AS duplicate_rows
    FROM duplicate_groups;
    """
).fetchone()


duplicate_groups, duplicate_rows = duplicate_stats


# ============================================================
# 6. Generate Markdown report
# ============================================================

type_lines = "\n".join(
    f"| {tx_type} | {count:,} |"
    for tx_type, count in transaction_types
)

if invalid_types:
    invalid_type_lines = "\n".join(
        f"| {tx_type} | {count:,} |"
        for tx_type, count in invalid_types
    )
else:
    invalid_type_lines = "| None | 0 |"


report = f"""# COFINFAD Raw Transaction Data Quality Report

## Source

`transactions_data.csv`

This report audits the raw transaction source before monthly
aggregation, feature engineering, or machine-learning modeling.

---

## 1. Dataset Summary

| Metric | Result |
|---|---:|
| Rows | {row_count:,} |
| Unique customers | {unique_customers:,} |
| First transaction date | {min_date} |
| Last transaction date | {max_date} |
| Null customer IDs | {null_customer_ids:,} |
| Null dates | {null_dates:,} |
| Null amounts | {null_amounts:,} |
| Null transaction types | {null_types:,} |

---

## 2. Transaction Types

| Type | Rows |
|---|---:|
{type_lines}

Expected values:

- Transfer
- Payment
- Withdrawal
- Deposit

---

## 3. Unexpected Transaction Types

| Type | Rows |
|---|---:|
{invalid_type_lines}

---

## 4. Transaction Amount Validation

| Metric | Result |
|---|---:|
| Minimum amount | {min_amount:,.2f} |
| Maximum amount | {max_amount:,.2f} |
| Average amount | {avg_amount:,.2f} |
| Negative amounts | {negative_amounts:,} |
| Zero amounts | {zero_amounts:,} |
| Non-positive amounts | {non_positive_amounts:,} |

Amounts are expected to be expressed in Colombian Pesos (COP).

---

## 5. Exact Duplicate Check

Exact duplicate definition:

`customer_id + date + amount + type`

| Metric | Result |
|---|---:|
| Duplicate groups | {duplicate_groups:,} |
| Additional duplicate rows | {duplicate_rows:,} |

Important:

Because this dataset does not contain a unique transaction ID,
identical rows are not automatically removed. Two identical rows
could potentially represent legitimate separate transactions.

---

## 6. Initial Data-Quality Status

Raw rows: **{row_count:,}**

Unique customers: **{unique_customers:,}**

Date range: **{min_date} → {max_date}**

The results above should be reviewed before proceeding to
customer-month aggregation.
"""


REPORT_PATH.write_text(report, encoding="utf-8")


# ============================================================
# Console output
# ============================================================

print()
print("COFINFAD RAW DATA AUDIT")
print("=" * 50)

print(f"Rows:               {row_count:,}")
print(f"Unique customers:   {unique_customers:,}")
print(f"Date range:          {min_date} -> {max_date}")

print()
print("Missing values")
print("-" * 50)
print(f"customer_id:         {null_customer_ids:,}")
print(f"date:                {null_dates:,}")
print(f"amount:              {null_amounts:,}")
print(f"type:                {null_types:,}")

print()
print("Duplicates")
print("-" * 50)
print(f"Duplicate groups:    {duplicate_groups:,}")
print(f"Duplicate rows:      {duplicate_rows:,}")

print()
print("Amount checks")
print("-" * 50)
print(f"Negative amounts:    {negative_amounts:,}")
print(f"Zero amounts:        {zero_amounts:,}")

print()
print("Transaction types")
print("-" * 50)

for tx_type, count in transaction_types:
    print(f"{tx_type:<20} {count:>12,}")

print()
print(f"Report written to:\n{REPORT_PATH}")