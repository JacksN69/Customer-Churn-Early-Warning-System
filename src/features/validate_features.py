"""Automated validation of customer_monthly / churn_features (Phases 3 and 5).

Checks (all computed on the Parquet outputs, reconciled to the raw CSV):
  * transaction count/amount reconcile to the raw transactions
  * customer-month grain is unique and every customer's months are contiguous
  * type counts/amounts add up, shares sum to 1 for active months
  * WeekendTransactionCount <= TransactionCount; ActiveDays rules
  * rolling 3M features re-derived independently (self-join, no window functions)
    for a seeded random sample of customers
  * InactiveNextMonth / Has6MonthHistory / EligibleForTraining re-derived
Also writes a 20-customer printout (private CSV) for manual verification.

Run: python -m src.features.validate_features
"""
import sys

import duckdb

from src import config

SAMPLE_CUSTOMERS = 300
PRINT_CUSTOMERS = 20
SEED = 42


def _p(path):
    return path.as_posix().replace("'", "''")


def run(sample_customers=SAMPLE_CUSTOMERS, write_report=True, verbose=True):
    db = duckdb.connect()
    db.execute(f"CREATE VIEW cm AS SELECT * FROM read_parquet('{_p(config.CUSTOMER_MONTHLY)}')")
    db.execute(f"CREATE VIEW cf AS SELECT * FROM read_parquet('{_p(config.CHURN_FEATURES)}')")
    db.execute(
        f"CREATE VIEW tx AS SELECT CAST(customer_id AS VARCHAR) customer_id, CAST(date AS DATE) date, "
        f"amount, type FROM read_csv_auto('{_p(config.RAW_DIR / 'transactions_data.csv')}', header=true)"
    )
    checks = {}

    raw_n, raw_amt = db.execute("SELECT COUNT(*), SUM(amount) FROM tx").fetchone()
    cm_n, cm_amt, rows, keys = db.execute(
        "SELECT SUM(TransactionCount), SUM(TotalAmount), COUNT(*), COUNT(DISTINCT (customer_id, Month)) FROM cm"
    ).fetchone()
    checks["SUM(TransactionCount) == raw transaction rows"] = (cm_n == raw_n, f"{cm_n:,} vs {raw_n:,}")
    checks["SUM(TotalAmount) == raw amount"] = (float(cm_amt) == float(raw_amt), f"{cm_amt} vs {raw_amt}")
    checks["customer-month keys unique"] = (rows == keys, f"{rows:,} rows / {keys:,} keys")
    checks["churn_features rows == customer_monthly rows"] = (
        db.execute("SELECT COUNT(*) FROM cf").fetchone()[0] == rows, "")
    noncontig = db.execute(
        "SELECT COUNT(*) FROM (SELECT customer_id, COUNT(*) n, MIN(Month) a, MAX(Month) b FROM cm GROUP BY 1) "
        "WHERE date_diff('month', a, b) + 1 <> n").fetchone()[0]
    checks["no missing months inside any customer timeline (zero months are explicit)"] = (noncontig == 0, f"{noncontig} gaps")
    zero_rows = db.execute("SELECT COUNT(*) FROM cm WHERE TransactionCount = 0").fetchone()[0]
    checks["zero-activity months exist as rows"] = (zero_rows > 0, f"{zero_rows:,} rows")

    v = db.execute("""SELECT
        COUNT(*) FILTER (WHERE TransactionCount <> TransferCount+PaymentCount+WithdrawalCount+DepositCount),
        COUNT(*) FILTER (WHERE ABS(TotalAmount-(TransferAmount+PaymentAmount+WithdrawalAmount+DepositAmount)) > 0.01),
        COUNT(*) FILTER (WHERE TransactionCount>0 AND ABS(PaymentShare+TransferShare+WithdrawalShare+DepositShare-1) > 1e-9),
        COUNT(*) FILTER (WHERE WeekendTransactionCount > TransactionCount),
        COUNT(*) FILTER (WHERE TransactionCount>0 AND ActiveDays < 1),
        COUNT(*) FILTER (WHERE TransactionCount=0 AND ActiveDays <> 0),
        COUNT(*) FILTER (WHERE (TransactionCount=0) <> (InactiveMonth=1))
        FROM cm""").fetchone()
    for label, n in zip(
        ["type counts sum to TransactionCount", "type amounts sum to TotalAmount",
         "shares sum to 100% for active months", "WeekendTransactionCount <= TransactionCount",
         "ActiveDays >= 1 when active", "ActiveDays = 0 when inactive", "InactiveMonth flag consistent"], v):
        checks[label] = (n == 0, f"{n} violations")

    # Independent recompute on a seeded sample of customers (no window functions).
    db.execute(f"""CREATE TEMP TABLE sample_ids AS SELECT customer_id FROM
        (SELECT DISTINCT customer_id FROM cf) ORDER BY hash(customer_id || '{SEED}') LIMIT {int(sample_customers)}""")
    r = db.execute("""
        WITH a AS (SELECT customer_id, Month, TransactionCount tc, TotalAmount ta FROM cf
                   WHERE customer_id IN (SELECT customer_id FROM sample_ids)),
        x AS (SELECT o.customer_id, o.Month,
          (SELECT SUM(y.tc) FROM a y WHERE y.customer_id=o.customer_id AND y.Month BETWEEN o.Month - INTERVAL 2 MONTH AND o.Month) rec_c,
          (SELECT SUM(y.tc) FROM a y WHERE y.customer_id=o.customer_id AND y.Month BETWEEN o.Month - INTERVAL 5 MONTH AND o.Month - INTERVAL 3 MONTH) prev_c,
          (SELECT SUM(y.ta) FROM a y WHERE y.customer_id=o.customer_id AND y.Month BETWEEN o.Month - INTERVAL 2 MONTH AND o.Month) rec_a,
          (SELECT SUM(y.ta) FROM a y WHERE y.customer_id=o.customer_id AND y.Month BETWEEN o.Month - INTERVAL 5 MONTH AND o.Month - INTERVAL 3 MONTH) prev_a,
          (SELECT y.tc FROM a y WHERE y.customer_id=o.customer_id AND y.Month = o.Month + INTERVAL 1 MONTH) next_c,
          (SELECT COUNT(*) FROM a y WHERE y.customer_id=o.customer_id AND y.Month <= o.Month) n_hist
          FROM a o)
        SELECT COUNT(*),
          COUNT(*) FILTER (WHERE x.rec_c <> f.TransactionCount_Recent3M),
          COUNT(*) FILTER (WHERE f.Has6MonthHistory=1 AND x.prev_c <> f.TransactionCount_Previous3M),
          COUNT(*) FILTER (WHERE f.Has6MonthHistory=1 AND ABS(x.rec_a - f.TotalAmount_Recent3M) > 0.01),
          COUNT(*) FILTER (WHERE f.Has6MonthHistory=1 AND ABS(x.prev_a - f.TotalAmount_Previous3M) > 0.01),
          COUNT(*) FILTER (WHERE f.Has6MonthHistory=1 AND f.TransactionCount_Previous3M > 0 AND
              ABS((x.rec_c - x.prev_c)::DOUBLE / x.prev_c - f.TransactionCount_3M_ChangePct) > 1e-9),
          COUNT(*) FILTER (WHERE f.Has6MonthHistory=0 AND f.TransactionCount_Previous3M IS NOT NULL),
          COUNT(*) FILTER (WHERE (f.Has6MonthHistory=1) <> (x.n_hist >= 6)),
          COUNT(*) FILTER (WHERE (f.TransactionCount>0 AND x.next_c=0) AND f.InactiveNextMonth IS DISTINCT FROM 1),
          COUNT(*) FILTER (WHERE (f.TransactionCount>0 AND x.next_c>0) AND f.InactiveNextMonth IS DISTINCT FROM 0),
          COUNT(*) FILTER (WHERE (x.next_c IS NULL OR f.TransactionCount=0) AND f.InactiveNextMonth IS NOT NULL),
          COUNT(*) FILTER (WHERE (f.Has6MonthHistory=1 AND f.TransactionCount>0 AND x.next_c IS NOT NULL) <> (f.EligibleForTraining=1))
        FROM x JOIN cf f USING (customer_id, Month)""").fetchone()
    names = ["Recent3M count", "Previous3M count", "Recent3M amount", "Previous3M amount",
             "3M count change %", "Previous3M NULL before 6 months", "Has6MonthHistory",
             "InactiveNextMonth = 1", "InactiveNextMonth = 0", "InactiveNextMonth NULL rules", "EligibleForTraining"]
    for n, mism in zip(names, r[1:]):
        checks[f"independent recompute: {n} ({r[0]:,} sampled rows)"] = (mism == 0, f"{mism} mismatches")

    # 20-customer printout for manual verification.
    printout = db.execute(f"""
        SELECT customer_id, strftime(Month,'%Y-%m') AS Month, TransactionCount, TotalAmount,
               TransactionCount_Recent3M AS Recent3M, TransactionCount_Previous3M AS Previous3M,
               ROUND(100 * TransactionCount_3M_ChangePct, 1) AS "3M Change %", InactiveNextMonth
        FROM cf WHERE customer_id IN (SELECT customer_id FROM sample_ids ORDER BY hash(customer_id) LIMIT {PRINT_CUSTOMERS})
          AND Has6MonthHistory = 1
        ORDER BY customer_id, Month""").fetchdf()
    config.REPORTS_DIR.mkdir(exist_ok=True)
    printout.to_csv(config.REPORTS_DIR / "sample_customer_histories_private.csv", index=False)

    failed = [k for k, (ok, _) in checks.items() if not ok]
    if write_report:
        lines = ["# ChurnFeatures / CustomerMonthly validation", "",
                 "Generated by `src/features/validate_features.py` from the Parquet outputs and raw CSV.", "",
                 "| Check | Result | Detail |", "|---|---|---|"]
        lines += [f"| {k} | {'PASS' if ok else 'FAIL'} | {d} |" for k, (ok, d) in checks.items()]
        lines += ["", f"Manual-verification sample (20 customers): `reports/sample_customer_histories_private.csv` "
                      "(private, git-ignored)."]
        (config.REPORTS_DIR / "feature_validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if verbose:
        for k, (ok, d) in checks.items():
            print(("PASS " if ok else "FAIL ") + k + (f" [{d}]" if d else ""))
        print(printout.head(18).to_string(index=False))
    return checks, failed


if __name__ == "__main__":
    _, failed = run()
    if failed:
        sys.exit(f"{len(failed)} validation check(s) failed")

