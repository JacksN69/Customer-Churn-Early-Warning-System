"""Temporal-leakage guards for the ML dataset (Phases 9, 12, 13, 14)."""
import json

import pandas as pd
import pytest

from src import config
from src.features import build_features

needs_data = pytest.mark.skipif(
    not (config.ML_DATASET.exists() and build_features.FEATURE_LIST_JSON.exists() and config.CHURN_FEATURES.exists()),
    reason="ML dataset not built")


def test_registry_candidates_exclude_forbidden_and_never_features():
    cands = set(build_features.registry_candidates())
    assert cands.isdisjoint(config.NEVER_FEATURES)
    reg = pd.read_csv(config.FEATURE_REGISTRY)
    blocked = set(reg[reg["historical_ml_policy"].isin(["FORBIDDEN", "EXCLUDE", "JOIN_KEY_ONLY", "METADATA_ONLY",
                                                        "JOIN_OR_DESCRIPTIVE_ONLY"])]["column"])
    assert cands.isdisjoint(blocked)


def test_registry_has_explicit_ml_allowed_column():
    reg = pd.read_csv(config.FEATURE_REGISTRY)
    assert {"ml_allowed", "reason", "time_available"} <= set(reg.columns)
    assert reg.loc[reg["column"] == "churn_probability", "ml_allowed"].eq("No").all()
    assert reg.loc[reg["column"] == "InactiveNextMonth", "ml_allowed"].eq("No").all()
    assert reg.loc[reg["column"] == "ObservedTenureMonths", "ml_allowed"].eq("No").all()


@needs_data
def test_model_features_are_clean_and_not_constant():
    meta = json.loads(build_features.FEATURE_LIST_JSON.read_text(encoding="utf-8"))
    feats = meta["features"]
    assert set(feats).isdisjoint(config.NEVER_FEATURES)
    assert not any(f.startswith("TopDriver") for f in feats)
    dim_cols = set(pd.read_parquet(config.DIM_CUSTOMER).columns) - {"customer_id"}
    assert set(feats).isdisjoint(dim_cols), "customer snapshot field leaked into model features"
    df = pd.read_parquet(config.ML_DATASET)
    lab = df[df["split"].isin(["train", "validation", "test"])]
    assert (lab[feats].nunique(dropna=True) > 1).all(), "constant feature kept"


@needs_data
def test_splits_are_chronological_and_scoring_month_is_unlabelled():
    df = pd.read_parquet(config.ML_DATASET)
    m = {s: (df.loc[df["split"] == s, "Month"].min(), df.loc[df["split"] == s, "Month"].max())
         for s in ("train", "validation", "test", "score")}
    assert m["train"][1] < m["validation"][0] <= m["validation"][1] < m["test"][0] <= m["test"][1] < m["score"][0]
    assert df.loc[df["split"] == "score", "target"].isna().all()
    assert df.loc[df["split"] != "score", "target"].notna().all()


@needs_data
def test_rolling_features_use_only_current_and_past_months():
    cf = pd.read_parquet(config.CHURN_FEATURES, columns=["customer_id", "Month", "TransactionCount", "TotalAmount"])
    cf["customer_id"] = cf["customer_id"].astype(str)
    cf["Month"] = pd.to_datetime(cf["Month"])
    df = pd.read_parquet(config.ML_DATASET)
    df["Month"] = pd.to_datetime(df["Month"])
    eligible = df[df["split"].isin(["train", "validation", "test", "score"])]
    assert not eligible.empty, "no rows available for temporal leakage validation"
    sample = eligible.sample(n=min(400, len(eligible)), random_state=config.RANDOM_STATE)
    cf = cf[cf["customer_id"].isin(set(sample["customer_id"]))]
    for _, r in sample.iterrows():
        hist = cf[(cf["customer_id"] == r["customer_id"]) & (cf["Month"] <= r["Month"])].sort_values("Month")
        last6, last3 = hist.tail(6), hist.tail(3)       # truncated at T: future rows never visible
        assert r["AvgTransactionCount_6M"] == pytest.approx(last6["TransactionCount"].mean())
        assert r["AvgAmount_3M"] == pytest.approx(float(last3["TotalAmount"].mean()), rel=1e-9)
        assert r["ActiveMonths_6M"] == (last6["TransactionCount"] > 0).sum()
        assert r["TransactionCountStdDev_3M"] == pytest.approx(last3["TransactionCount"].std(ddof=1), nan_ok=True)
