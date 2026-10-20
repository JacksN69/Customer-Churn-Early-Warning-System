"""Unit tests for the feature SQL on tiny synthetic data (hand-computable).

Customer A  Jan10 Feb12 Mar8 Apr6 May4 Jun2 Jul0 Aug0 Sep3   (April/May style zero rows)
Customer B  one transaction in Sep (defines the final observed month)
Customer D  Jan1 Feb1 Mar1 then nothing (extended inactivity)
"""
import datetime as dt

import duckdb
import pandas as pd
import pytest

from src import config

FEATURES_DIR = config.PROJECT_ROOT / "src" / "features"
TYPES = ["Transfer", "Payment", "Withdrawal", "Deposit"]


def _tx_rows():
    rows = []

    def add(cust, month, n, days=None):
        for i in range(n):
            day = days[i] if days else 1 + i
            rows.append((cust, dt.date(2023, month, day), 100 * (1 + i % 3), TYPES[i % 4]))

    for m, n in zip(range(1, 10), [10, 12, 8, 6, 4, 2, 0, 0, 3]):
        add("A", m, n, days=[5, 20] if m == 6 else None)
    add("B", 9, 1)
    for m in (1, 2, 3):
        add("D", m, 1)
    return rows


@pytest.fixture(scope="module")
def feats():
    db = duckdb.connect()
    db.execute("CREATE TABLE tx (customer_id VARCHAR, date DATE, amount DECIMAL(38,2), type VARCHAR)")
    db.executemany("INSERT INTO tx VALUES (?, ?, ?, ?)", _tx_rows())
    db.execute((FEATURES_DIR / "customer_monthly_reference.sql").read_text(encoding="utf-8"))
    db.execute((FEATURES_DIR / "churn_features.sql").read_text(encoding="utf-8"))
    df = db.execute("SELECT * FROM expected_features").fetchdf()
    return df.set_index(["customer_id", df["Month"].dt.strftime("%Y-%m")]), len(_tx_rows())


def row(feats, cust, month):
    return feats[0].loc[(cust, month)]


def test_transactions_reconcile(feats):
    df, n_tx = feats
    assert df["TransactionCount"].sum() == n_tx


def test_zero_months_are_explicit_rows(feats):
    df, _ = feats
    assert len(df.loc["A"]) == 9                      # Jan..Sep, nothing dropped
    assert row(feats, "A", "2023-07")["TransactionCount"] == 0
    assert row(feats, "A", "2023-08")["TransactionCount"] == 0
    assert row(feats, "A", "2023-07")["ActiveDays"] == 0
    assert row(feats, "A", "2023-07")["InactiveMonth"] == 1


def test_three_month_windows_match_hand_calculation(feats):
    jun = row(feats, "A", "2023-06")
    assert jun["TransactionCount_Recent3M"] == 12     # Apr6 + May4 + Jun2
    assert jun["TransactionCount_Previous3M"] == 30   # Jan10 + Feb12 + Mar8
    assert jun["TransactionCount_3M_ChangePct"] == pytest.approx(-0.60)
    assert jun["TransactionDecline50Pct"] == 1
    sep = row(feats, "A", "2023-09")
    assert sep["TransactionCount_Recent3M"] == 3
    assert sep["TransactionCount_Previous3M"] == 12
    assert sep["TransactionCount_3M_ChangePct"] == pytest.approx(-0.75)


def test_previous3m_is_null_before_six_months_of_history(feats):
    mar = row(feats, "A", "2023-03")
    assert mar["Has6MonthHistory"] == 0
    assert mar["TransactionCount_Previous3M"] != mar["TransactionCount_Previous3M"]  # NaN


def test_primary_target_definition(feats):
    assert row(feats, "A", "2023-05")["InactiveNextMonth"] == 0   # June active
    assert row(feats, "A", "2023-06")["InactiveNextMonth"] == 1   # July zero
    jul = row(feats, "A", "2023-07")["InactiveNextMonth"]
    sep = row(feats, "A", "2023-09")["InactiveNextMonth"]
    assert pd.isna(jul)                                          # inactive at T -> null
    assert pd.isna(sep)                                          # T+1 unavailable -> null


def test_extended_inactivity_is_separate_future_label(feats):
    assert row(feats, "D", "2023-03")["ExtendedInactivityNext3Months"] == 1
    assert row(feats, "D", "2023-02")["ExtendedInactivityNext3Months"] == 0
    assert row(feats, "A", "2023-06")["ExtendedInactivityNext3Months"] == 0   # Sep active


def test_eligibility(feats):
    assert row(feats, "A", "2023-06")["EligibleForTraining"] == 1
    assert row(feats, "A", "2023-07")["EligibleForTraining"] == 0     # inactive
    assert row(feats, "A", "2023-09")["EligibleForTraining"] == 0     # no T+1 observed
    assert row(feats, "A", "2023-03")["EligibleForTraining"] == 0     # <6 months


def test_recency_uses_only_past_transactions(feats):
    assert row(feats, "A", "2023-06")["DaysSinceLastTransaction"] == 10   # Jun 30 - Jun 20
    assert row(feats, "A", "2023-07")["DaysSinceLastTransaction"] == 41   # Jul 31 - Jun 20
    assert row(feats, "A", "2023-07")["ConsecutiveInactiveMonths"] == 1
    assert row(feats, "A", "2023-08")["ConsecutiveInactiveMonths"] == 2


def test_row_level_invariants(feats):
    df, _ = feats
    parts = df[["TransferCount", "PaymentCount", "WithdrawalCount", "DepositCount"]].sum(axis=1)
    assert (parts == df["TransactionCount"]).all()
    amount_parts = df[["TransferAmount", "PaymentAmount", "WithdrawalAmount", "DepositAmount"]].sum(axis=1)
    assert ((amount_parts - df["TotalAmount"].astype(float)).abs() < 0.01).all()
    active = df[df["TransactionCount"] > 0]
    shares = active[["PaymentShare", "TransferShare", "WithdrawalShare", "DepositShare"]].sum(axis=1)
    assert ((shares - 1).abs() < 1e-9).all()
    assert (df["WeekendTransactionCount"] <= df["TransactionCount"]).all()
    assert (active["ActiveDays"] >= 1).all()
    assert (df[df["TransactionCount"] == 0]["ActiveDays"] == 0).all()


@pytest.mark.skipif(not config.CHURN_FEATURES.exists() or not (config.RAW_DIR / "transactions_data.csv").exists(),
                    reason="processed Parquet / raw CSV not available")
def test_full_dataset_validation_has_no_failures():
    from src.features import validate_features
    _, failed = validate_features.run(sample_customers=100, write_report=False, verbose=False)
    assert failed == []
