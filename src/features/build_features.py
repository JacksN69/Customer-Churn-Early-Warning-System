"""Build the ML dataset (Phases 12-13).

Unit: customer-month observation (not unique customer).
Rows: EligibleForTraining = 1 (labelled, T = Jun..Nov) plus the scoring month
      (Dec 2023: active customers with 6 months of history, label unobserved).
Features: registry-approved transaction features + engineered rolling features
          (current/past months only) + null indicators. Constant features
          (nunique <= 1 over the labelled rows) are detected and removed.

Run: python -m src.features.build_features
"""
import json

import duckdb
import pandas as pd

from src import config
from src.features.feature_definitions import ENGINEERED_FEATURES, NULL_INDICATORS, TRANSACTION_TYPES

FEATURE_LIST_JSON = config.PROCESSED_DIR / "ml_feature_list.json"


def _p(path):
    return path.as_posix().replace("'", "''")


def registry_candidates():
    reg = pd.read_csv(config.FEATURE_REGISTRY)
    cf = reg[reg["table"] == "ChurnFeatures"]
    ok = cf[cf["historical_ml_policy"].isin(["ML_CANDIDATE", "ML_CANDIDATE_WITH_NULL_INDICATOR"])]
    return [c for c in ok["column"] if c not in config.NEVER_FEATURES]


def assign_split(period: pd.Series) -> pd.Series:
    out = pd.Series("unused", index=period.index)
    out[period.isin(config.TRAIN_MONTHS)] = "train"
    out[period.isin(config.VALIDATION_MONTHS)] = "validation"
    out[period.isin(config.TEST_MONTHS)] = "test"
    out[period == config.SCORING_MONTH] = "score"
    return out


def build(verbose=True):
    base = registry_candidates()
    categorical = "PreferredTransactionType"
    numeric_base = [c for c in base if c != categorical]
    db = duckdb.connect()
    w3 = "PARTITION BY customer_id ORDER BY Month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW"
    w6 = "PARTITION BY customer_id ORDER BY Month ROWS BETWEEN 5 PRECEDING AND CURRENT ROW"
    type_div = " + ".join(
        f"(SUM({t}Count) OVER ({w3}) > 0)::INTEGER" for t in TRANSACTION_TYPES)
    shares = ",\n".join(
        f"SUM({t}Count) OVER ({w3})::DOUBLE / NULLIF(SUM(TransactionCount) OVER ({w3}), 0) AS Recent3M{t}Share"
        for t in ["Payment", "Transfer", "Withdrawal", "Deposit"])
    indicators = ",\n".join(f"({src} IS NULL)::INTEGER AS {dst}" for src, dst in NULL_INDICATORS.items())
    pref = ",\n".join(
        f"CASE WHEN PreferredTransactionType='{t}' THEN 1.0 ELSE 0.0 END AS PreferredType_{t}"
        for t in TRANSACTION_TYPES)
    num_select = ",\n".join(f'CAST("{c}" AS DOUBLE) AS "{c}"' for c in numeric_base)
    sql = f"""
    WITH windowed AS (
      SELECT *,
        AVG(TransactionCount) OVER ({w3}) AS AvgTransactionCount_3M,
        AVG(TransactionCount) OVER ({w6}) AS AvgTransactionCount_6M,
        AVG(TotalAmount) OVER ({w3}) AS AvgAmount_3M,
        AVG(TotalAmount) OVER ({w6}) AS AvgAmount_6M,
        SUM((TransactionCount > 0)::INTEGER) OVER ({w3}) AS ActiveMonths_3M,
        SUM((TransactionCount > 0)::INTEGER) OVER ({w6}) AS ActiveMonths_6M,
        STDDEV_SAMP(TransactionCount) OVER ({w3}) AS TransactionCountStdDev_3M,
        STDDEV_SAMP(TotalAmount) OVER ({w3}) AS AmountStdDev_3M,
        {type_div} AS TransactionTypeDiversity_3M,
        {shares}
      FROM read_parquet('{_p(config.CHURN_FEATURES)}')
    )
    SELECT CAST(customer_id AS VARCHAR) AS customer_id, Month,
           strftime(Month, '%Y-%m') AS period,
           InactiveNextMonth AS target,
           {num_select},
           {pref},
           {indicators},
           CAST(AvgTransactionCount_3M AS DOUBLE) AS AvgTransactionCount_3M,
           CAST(AvgTransactionCount_6M AS DOUBLE) AS AvgTransactionCount_6M,
           CAST(AvgAmount_3M AS DOUBLE) AS AvgAmount_3M,
           CAST(AvgAmount_6M AS DOUBLE) AS AvgAmount_6M,
           CAST(ActiveMonths_3M AS DOUBLE) AS ActiveMonths_3M,
           CAST(ActiveMonths_6M AS DOUBLE) AS ActiveMonths_6M,
           CAST(TransactionCountStdDev_3M AS DOUBLE) AS TransactionCountStdDev_3M,
           CAST(AmountStdDev_3M AS DOUBLE) AS AmountStdDev_3M,
           CAST(TransactionTypeDiversity_3M AS DOUBLE) AS TransactionTypeDiversity_3M,
           Recent3MPaymentShare, Recent3MTransferShare, Recent3MWithdrawalShare, Recent3MDepositShare
    FROM windowed
    WHERE EligibleForTraining = 1
       OR (strftime(Month, '%Y-%m') = '{config.SCORING_MONTH}' AND TransactionCount > 0 AND Has6MonthHistory = 1)
    ORDER BY Month, customer_id
    """
    df = db.execute(sql).fetchdf()
    df["split"] = assign_split(df["period"])
    # Label sanity: labelled splits must have an observed target; scoring rows must not.
    labelled = df["split"].isin(["train", "validation", "test"])
    assert df.loc[labelled, "target"].notna().all(), "labelled row without target"
    assert df.loc[df["split"] == "score", "target"].isna().all(), "scoring month must be unlabeled"
    assert not (df["split"] == "unused").any(), "unexpected months in dataset"

    candidates = (numeric_base + [f"PreferredType_{t}" for t in TRANSACTION_TYPES]
                  + list(NULL_INDICATORS.values()) + list(ENGINEERED_FEATURES))
    banned = set(candidates) & config.NEVER_FEATURES
    assert not banned, f"never-features in candidate list: {banned}"
    nunique = df.loc[labelled, candidates].nunique(dropna=True)
    constant = nunique[nunique <= 1].index.tolist()
    features = [c for c in candidates if c not in constant]

    df["target"] = df["target"].astype("Int64")
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(config.ML_DATASET, index=False)
    FEATURE_LIST_JSON.write_text(json.dumps(
        {"features": features, "removed_constant": constant,
         "engineered": list(ENGINEERED_FEATURES), "null_indicators": list(NULL_INDICATORS.values())}, indent=2),
        encoding="utf-8")

    by_split = df.groupby("split").agg(rows=("customer_id", "size"), customers=("customer_id", "nunique"),
                                       positives=("target", lambda s: int(s.fillna(0).sum()))).reindex(
        ["train", "validation", "test", "score"])
    by_split["positive_rate"] = (by_split["positives"] / by_split["rows"]).where(by_split.index != "score")
    by_month = df.groupby("period").agg(rows=("customer_id", "size"), positives=("target", lambda s: int(s.fillna(0).sum())))
    lines = ["# ML dataset (customer-month observations)", "",
             "Generated by `src/features/build_features.py`. Unit = customer-month; the same customer appears in many months.", "",
             "## Rows by chronological split", "", "| Split | Months | Rows | Customers | Positives | Positive rate |", "|---|---|---:|---:|---:|---:|"]
    months = {"train": config.TRAIN_MONTHS, "validation": config.VALIDATION_MONTHS,
              "test": config.TEST_MONTHS, "score": [config.SCORING_MONTH]}
    for s, r in by_split.iterrows():
        rate = "n/a (unlabelled)" if s == "score" else f"{r.positive_rate:.2%}"
        lines.append(f"| {s} | {', '.join(months[s])} | {int(r.rows):,} | {int(r.customers):,} | "
                     f"{int(r.positives):,} | {rate} |")
    lines += ["", "## Rows by month", "", "| Month | Rows | Positives |", "|---|---:|---:|"]
    lines += [f"| {m} | {int(r.rows):,} | {int(r.positives):,} |" for m, r in by_month.iterrows()]
    lines += ["", f"## Feature set ({len(features)} features)", "",
              f"Constant features removed automatically (`nunique <= 1` over labelled rows): "
              f"{', '.join(constant) if constant else 'none among registry candidates'}.", "",
              "Registry-excluded before modelling: InactiveMonth, ConsecutiveInactiveMonths, Has6MonthHistory, "
              "EligibleForTraining (constant among eligible rows), ObservedTenureMonths (calendar proxy), "
              "InactiveNextMonth, ExtendedInactivityNext3Months, churn_probability, identifiers and dates.", "",
              "```", ", ".join(features), "```", ""]
    (config.REPORTS_DIR / "ml_dataset.md").write_text("\n".join(lines), encoding="utf-8")
    if verbose:
        print(by_split)
        print("features:", len(features), "constant removed:", constant)
    return df, features


def load_dataset():
    """Return (dataframe, feature list). Builds the dataset if it does not exist."""
    if not config.ML_DATASET.exists() or not FEATURE_LIST_JSON.exists():
        build(verbose=False)
    meta = json.loads(FEATURE_LIST_JSON.read_text(encoding="utf-8"))
    return pd.read_parquet(config.ML_DATASET), meta["features"]


if __name__ == "__main__":
    build()

