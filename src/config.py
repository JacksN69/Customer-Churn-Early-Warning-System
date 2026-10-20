"""Shared paths and modelling policy for the churn early-warning pipeline.

All modelling decisions that affect results live here so they are visible,
documented and reproducible. Paths resolve relative to PROJECT_ROOT.
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
REPORTS_DIR = PROJECT_ROOT / "reports"
MODELS_DIR = PROJECT_ROOT / "models"
DOCS_DIR = PROJECT_ROOT / "docs"

CUSTOMER_MONTHLY = PROCESSED_DIR / "customer_monthly.parquet"
CHURN_FEATURES = PROCESSED_DIR / "churn_features.parquet"
DIM_CUSTOMER = PROCESSED_DIR / "dim_customer.parquet"
ML_DATASET = PROCESSED_DIR / "ml_dataset.parquet"
FEATURE_REGISTRY = DOCS_DIR / "FEATURE_REGISTRY.csv"

TARGET = "InactiveNextMonth"
ID_COLUMNS = ["customer_id", "Month"]

# Chronological design (observation month T). Labels exist for T = Jun..Nov 2023.
TRAIN_MONTHS = ["2023-06", "2023-07", "2023-08", "2023-09"]
VALIDATION_MONTHS = ["2023-10"]
TEST_MONTHS = ["2023-11"]
SCORING_MONTH = "2023-12"          # January 2024 outcome is unobserved
PREDICTION_MONTH = "2024-01"

# Columns that must never be model inputs. Verified by tests/test_leakage.py.
NEVER_FEATURES = {
    "InactiveNextMonth", "ExtendedInactivityNext3Months", "EligibleForTraining",
    "Has6MonthHistory", "churn_probability", "customer_id", "Month",
    "CustomerStartMonth", "FirstTransactionDate", "LastTransactionDate", "_i",
    # Calendar proxy: ~80% of customers start in Jan 2023, so tenure == month index
    # and test/scoring months fall outside the training range (see README).
    "ObservedTenureMonths",
}

# Capacity-based risk tiers: share of scored customers the retention team can
# contact. Cutoffs are learned on the validation month, never on the test month.
RISK_TIER_CAPACITY = {"Critical": 0.05, "High": 0.10, "Medium": 0.30}  # cumulative top-share
OPERATING_CAPACITY = 0.10          # default outreach capacity (top 10% of active customers)
# Placeholder unit costs for the cost-based threshold; replace with business values.
COST_MISSED_INACTIVE = 5.0
COST_UNNEEDED_CONTACT = 1.0

# Static customer profile fields used ONLY in the clearly labelled
# "behavior+static_profile" experiment (never in the production feature set).
PROFILE_EXPERIMENT_COLUMNS = [
    "age", "gender", "location", "income_bracket", "occupation",
    "education_level", "marital_status", "household_size", "acquisition_channel",
]

RANDOM_STATE = 42

