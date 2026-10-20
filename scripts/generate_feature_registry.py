"""Generate leakage-aware data dictionary for transaction and customer features."""
import csv
import sys
from pathlib import Path
import duckdb

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.features.feature_definitions import ENGINEERED_FEATURES, NULL_INDICATORS
OUT=ROOT/"docs"/"FEATURE_REGISTRY.csv"
db=duckdb.connect()
p=lambda x:x.as_posix().replace("'","''")
future={"InactiveNextMonth","ExtendedInactivityNext3Months"}
constant={"InactiveMonth","ConsecutiveInactiveMonths","Has6MonthHistory","EligibleForTraining"}
metadata={"customer_id","Month","CustomerStartMonth","FirstTransactionDate","LastTransactionDate"}
ratio={"TransactionCountChangePct","TotalAmountChangePct","TransactionCount_3M_ChangePct","TotalAmount_3M_ChangePct"}
# ~80% of customers first appear in Jan 2023, so tenure equals the calendar-month index
# and test/scoring months fall outside the training range.
calendar_proxy={"ObservedTenureMonths"}
dim_source=ROOT/"data"/"processed"/"dim_customer.parquet"
fact_source=ROOT/"data"/"processed"/"churn_features.parquet"
rows=[]
for table,source in [("ChurnFeatures",fact_source),("DimCustomer",dim_source)]:
    for name,type_name,*_ in db.execute(f"DESCRIBE SELECT * FROM read_parquet('{p(source)}')").fetchall():
        if table=="ChurnFeatures":
            if name in future:use,why="FORBIDDEN","Future outcome label; only use as supervised target or descriptive target, never a predictor"
            elif name in calendar_proxy:use,why="EXCLUDE","Calendar-month proxy (left-censored observation window); unseen values appear in test and scoring months"
            elif name in constant:use,why="EXCLUDE","Constant or eligibility information for active training population"
            elif name in metadata:use,why="METADATA_ONLY","Identifier, observation date, or redundant observed first-transaction date; never model raw identifiers/dates"
            elif name in ratio:use,why="ML_CANDIDATE_WITH_NULL_INDICATOR","Previous denominator zero can yield undefined null; impute on train fold only and preserve indicator"
            else:use,why="ML_CANDIDATE","Behavioral input known at end of T; verify prediction cutoff and training split"
            availability="End of month T" if name not in future else "Post-T; future month(s)"
        else:
            use="JOIN_OR_DESCRIPTIVE_ONLY" if name!="customer_id" else "JOIN_KEY_ONLY"
            why=("Customer key for dimension join; do not model as category" if name=="customer_id" else
                "Undated customer-level snapshot: cannot establish historical availability at T. Do not train on this field.")
            availability="Unproven as of T"
        rows.append((table,name,type_name,availability,use,why))
rows.append(("customer_data raw","churn_probability","vendor-supplied numeric","Unknown/Future possible","FORBIDDEN","Neither target nor ML feature; omitted from processed DimCustomer"))
for name in ("CreditUtilizationStatus","FeatureRequestsDisplay","ComplaintTopicsDisplay"):
    rows.append(("DimCustomer (Power BI calculated)",name,"STRING","Snapshot display time unknown","JOIN_OR_DESCRIPTIVE_ONLY",
                 "UI-only display of original null values; never an ML predictor; original nullable column unchanged"))
for name,hypothesis in ENGINEERED_FEATURES.items():
    rows.append(("MLDataset (Python, src/features/build_features.py)",name,"DOUBLE","End of month T (current and past months only)","ML_CANDIDATE","Hypothesis: "+hypothesis))
for source_col,name in NULL_INDICATORS.items():
    rows.append(("MLDataset (Python, src/features/build_features.py)",name,"INTEGER","End of month T","ML_CANDIDATE",f"Indicator that {source_col} is undefined (zero denominator)"))
def ml_allowed(policy,table):
    if policy.startswith("ML_CANDIDATE"):return "Yes"
    if table.startswith("DimCustomer") and policy=="JOIN_OR_DESCRIPTIVE_ONLY":return "Conditional (descriptive/BI only until as-of timing is proven)"
    return "No"
OUT.parent.mkdir(parents=True,exist_ok=True)
with OUT.open("w",newline="",encoding="utf-8") as f:
    w=csv.writer(f)
    w.writerow(("table","column","data_type","time_available","historical_ml_policy","reason","ml_allowed"))
    w.writerows(row+(ml_allowed(row[4],row[0]),) for row in rows)
print("FEATURE_REGISTRY_ENTRIES",len(rows),"FILE",OUT)
assert all(row[4] != "ML_CANDIDATE" for row in rows if row[0]=="DimCustomer")
