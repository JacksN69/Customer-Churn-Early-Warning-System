# Next user action — 20 October 2026

1. **Open and Save the 6-Page German IBCS Power BI Dashboard**:
   - All 6 German enterprise report pages (`01 Management-Übersicht`, `02 Frühwarnsystem`, `03 Kundenprofil 360°`, `04 Risikotreiber`, `05 Modellgüte`, `06 Datenqualität` — 74 visuals total, IBCS 2.0 / ISO 24896:2026 palette, `1440 × 810 px`) are already injected into `powerbi/Customer Churn Early-Warning System.pbix`.
   - Open `powerbi/Customer Churn Early-Warning System.pbix` in Power BI Desktop, then run:
     ```powershell
     powershell -ExecutionPolicy Bypass -File scripts\build_powerbi_model.ps1
     ```
     and press **`Ctrl+S`** in Power BI Desktop to persist the newly added semantic model tables (`ChurnPredictions`, `FeatureImportance`, `ModelExperiments`, `FeatureRegistry`, `DriverRankSlot`, `CalibrationDeciles`, `ConfusionMatrixTable`, `ThresholdPolicyTable`, `DataQualityChecks`), relationships, calculated columns, and 51 German DAX measures inside the `.pbix` binary.
2. **Re-running the Python ML + Power BI Asset Pipeline**:
   - `.\.venv\Scripts\python.exe -m src.pipeline.run_pipeline --skip-etl`
   - `.\.venv\Scripts\python.exe scripts\prepare_powerbi_outputs.py`
   - `.\.venv\Scripts\python.exe scripts\build_powerbi_report_pages.py`
3. Set real retention costs and capacity in `src/config.py` (`COST_*`, `OPERATING_CAPACITY`, `RISK_TIER_CAPACITY`) if you want different thresholds.
