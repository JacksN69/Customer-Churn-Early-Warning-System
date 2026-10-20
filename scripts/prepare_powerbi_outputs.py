"""Enrich outputs/churn_predictions.parquet with dashboard helper columns
and inspect the current PBIX Report/definition structure.
"""
import json
import os
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
PROCESSED = ROOT / "data" / "processed"


def enrich_predictions():
    preds = pd.read_parquet(OUTPUTS / "churn_predictions.parquet")
    shap_df = pd.read_parquet(OUTPUTS / "shap_explanations.parquet")
    ml = pd.read_parquet(PROCESSED / "ml_dataset.parquet")

    # Drop any old enriched or TopDriver columns before clean merge
    drop_cols = [
        c for c in preds.columns
        if c.startswith("TopDriver") or c in {
            "TransactionCount_Previous3M", "PreviousTransactionCount",
            "AvgTransactionCount_3M", "AvgTransactionCount_6M",
            "PreferredTransactionType", "PaymentCount", "TransferCount",
            "WithdrawalCount", "DepositCount", "RiskDecile", "IsTop10PctRank",
            "RiskLevelSort", "PriorityQuadrantSort",
            "ValueSegment", "ValueSegmentSort", "RiskGroup2x2", "RiskGroup2x2Sort",
        }
    ]
    preds = preds.drop(columns=drop_cols)

    ml_sub = ml[[
        "customer_id", "Month",
        "TransactionCount_Previous3M", "PreviousTransactionCount",
        "AvgTransactionCount_3M", "AvgTransactionCount_6M",
        "PreferredType_Transfer", "PreferredType_Payment",
        "PreferredType_Withdrawal", "PreferredType_Deposit",
        "PaymentCount", "TransferCount", "WithdrawalCount", "DepositCount",
    ]].copy()
    ml_sub["customer_id"] = ml_sub["customer_id"].astype(str)
    ml_sub["Month"] = pd.to_datetime(ml_sub["Month"])
    ml_sub["PreferredTransactionType"] = np.select(
        [
            ml_sub["PreferredType_Transfer"] == 1.0,
            ml_sub["PreferredType_Payment"] == 1.0,
            ml_sub["PreferredType_Withdrawal"] == 1.0,
            ml_sub["PreferredType_Deposit"] == 1.0,
        ],
        ["Transfer", "Payment", "Withdrawal", "Deposit"],
        default="Transfer",
    )
    ml_sub = ml_sub.drop(columns=[
        "PreferredType_Transfer", "PreferredType_Payment",
        "PreferredType_Withdrawal", "PreferredType_Deposit",
    ])

    preds["customer_id"] = preds["customer_id"].astype(str)
    preds["Month"] = pd.to_datetime(preds["Month"])
    merged = preds.merge(ml_sub, on=["customer_id", "Month"], how="left", validate="one_to_one")

    n_month = merged.groupby("Month")["InactiveProbability"].transform("count")
    merged["RiskDecile"] = np.ceil(merged["RiskRank"] * 10.0 / n_month).clip(1, 10).astype(int)
    merged["IsTop10PctRank"] = (merged["RiskRank"] <= np.ceil(n_month * 0.10)).astype(int)
    merged["RiskLevelSort"] = merged["RiskLevel"].map(
        {"Critical": 1, "High": 2, "Medium": 3, "Low": 4}
    ).astype(int)
    merged["PriorityQuadrantSort"] = merged["PriorityQuadrant"].map({
        "High value + High risk": 1,
        "Low value + High risk": 2,
        "High value + Low risk": 3,
        "Low value + Low risk": 4,
    }).astype(int)
    high_val = merged["PriorityQuadrant"].str.startswith("High value")
    high_rsk = merged["RiskLevel"].isin(["Critical", "High"])
    merged["ValueSegment"] = np.where(high_val, "Hoher Wert (>= Median 3M)", "Niedriger Wert (< Median 3M)")
    merged["ValueSegmentSort"] = np.where(high_val, 1, 2).astype(int)
    merged["RiskGroup2x2"] = np.where(high_rsk, "Hohes / Kritisches Risiko", "Niedriges / Mittleres Risiko")
    merged["RiskGroup2x2Sort"] = np.where(high_rsk, 2, 1).astype(int)

    shap_df["customer_id"] = shap_df["customer_id"].astype(str)
    shap_df["Month"] = pd.to_datetime(shap_df["Month"])
    merged = merged.merge(
        shap_df, on=["customer_id", "Month", "ScoreType"], how="left", validate="one_to_one"
    )
    assert merged["TopDriver1"].notna().all(), "Missing TopDriver1"
    assert merged["PreferredTransactionType"].notna().all(), "Missing PreferredTransactionType"

    merged.to_parquet(OUTPUTS / "churn_predictions.parquet", index=False)
    dec = merged[merged["ScoreType"] == "Production (Dec 2023 -> Jan 2024)"]
    print("ENRICHED churn_predictions.parquet:", merged.shape)
    print("Dec count:", len(dec),
          "| High/Crit:", int(dec["RiskLevel"].isin(["Critical", "High"]).sum()),
          "| HighVal+HighRisk:", int((dec["PriorityQuadrant"] == "High value + High risk").sum()),
          "| Top10PctRank:", int(dec["IsTop10PctRank"].sum()))

    # Also write Parquet versions of FeatureImportance, ModelExperiments, FeatureRegistry
    fi = pd.read_csv(OUTPUTS / "feature_importance.csv")
    fi["IsTop15"] = np.where(fi["rank"] <= 15, "Ja", "Nein")
    fi.to_parquet(OUTPUTS / "feature_importance.parquet", index=False)

    me = pd.read_csv(ROOT / "reports" / "model_experiments.csv")
    # Keep latest run_id rows for clean model comparison
    latest_run = me["run_id"].iloc[-1]
    me_latest = me[me["run_id"] == latest_run].copy()
    name_map = {
        "lightgbm_leaves31": "LightGBM (leaves=31, ausgewählt)",
        "lightgbm_leaves15": "LightGBM (leaves=15)",
        "lightgbm_with_static_profile": "LightGBM + Statisches Profil (Experiment)",
        "logreg_unweighted": "Logistische Regression (Ungewichtet)",
        "logreg_balanced": "Logistische Regression (Class-Balanced)",
    }
    me_latest["Modellvariante"] = me_latest["model_name"].map(name_map).fillna(me_latest["model_name"])
    me_latest["ModellStatus"] = np.where(
        me_latest["selected"], "Ausgewählt (Produktion)",
        np.where(me_latest["model_name"].str.contains("profile"), "Nur Experiment (Leakage-Prüfung)", "Kandidat")
    )
    me_latest.to_parquet(OUTPUTS / "model_experiments.parquet", index=False)

    fr = pd.read_csv(ROOT / "docs" / "FEATURE_REGISTRY.csv")
    fr.to_parquet(OUTPUTS / "feature_registry.parquet", index=False)

    pq_dir = ROOT / "powerquery"
    tables_meta = {}
    for tbl_name, name, rel_path in [
        ("ChurnPredictions", "churn_predictions.m.txt", r"outputs\churn_predictions.parquet"),
        ("FeatureImportance", "feature_importance.m.txt", r"outputs\feature_importance.parquet"),
        ("ModelExperiments", "model_experiments.m.txt", r"outputs\model_experiments.parquet"),
        ("FeatureRegistry", "feature_registry.m.txt", r"outputs\feature_registry.parquet"),
    ]:
        full_p = str(ROOT / rel_path)
        m_code = f'let\n    Source = Parquet.Document(File.Contents("{full_p}"))\nin\n    Source'
        (pq_dir / name).write_text(m_code, encoding="utf-8")
        df_tmp = pd.read_parquet(ROOT / rel_path)
        cols = []
        for col, dtype in df_tmp.dtypes.items():
            s_dtype = str(dtype)
            if "datetime" in s_dtype:
                tom_type = "DateTime"
            elif "int" in s_dtype.lower():
                tom_type = "Int64"
            elif "float" in s_dtype.lower():
                tom_type = "Double"
            elif "bool" in s_dtype.lower():
                tom_type = "Boolean"
            else:
                tom_type = "String"
            cols.append({"name": col, "dataType": tom_type})
        tables_meta[tbl_name] = {"path": full_p, "columns": cols}

    (OUTPUTS / "powerbi_table_schemas.json").write_text(
        json.dumps(tables_meta, indent=2), encoding="utf-8"
    )
    print("Wrote Parquet + powerquery/*.m.txt + outputs/powerbi_table_schemas.json.")


def inspect_env():
    pq_files = sorted(p.name for p in (ROOT / "powerquery").iterdir() if p.is_file())
    print("powerquery files:", pq_files)

    pbix = ROOT / "powerbi" / "Customer Churn Early-Warning System.pbix"
    with zipfile.ZipFile(pbix, "r") as zf:
        names = zf.namelist()
        print("PBIX entries:", names)
        for name in names:
            if name.startswith("Report/definition/") and name.endswith(".json"):
                print(f"--- {name} ---")
                print(zf.read(name).decode("utf-8"))

    ws_root = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Power BI Desktop" / "AnalysisServicesWorkspaces"
    ports = list(ws_root.rglob("msmdsrv.port.txt")) if ws_root.exists() else []
    print("Active PBI Desktop ports:", [str(p) for p in ports])

    pbi_bin = Path(r"C:\Program Files\Microsoft Power BI Desktop\bin")
    if pbi_bin.exists():
        schemas = list(pbi_bin.rglob("*schema*.json")) + list(pbi_bin.rglob("*visualContainer*"))
        print("Local PBI schemas:", [str(s) for s in schemas[:25]])


if __name__ == "__main__":
    enrich_predictions()
    inspect_env()
