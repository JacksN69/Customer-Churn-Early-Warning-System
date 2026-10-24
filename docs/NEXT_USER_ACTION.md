# Local dashboard verification — 20 October 2026

Requirements: Windows, Power BI Desktop, the local PBIX and private source datasets. The public repository includes generation code and model metadata but not a redistributable PBIX. Close other Power BI reports before running the model-update script to avoid selecting the wrong live model.

1. **Generate and verify the six-page Power BI report locally**:
   - The report generator defines six German-language pages (`01 Management-Übersicht`, `02 Frühwarnsystem`, `03 Kundenprofil 360°`, `04 Risikotreiber`, `05 Modellgüte`, `06 Datenqualität`; 74 visuals, `1440 × 810 px`). This repository does not include the PBIX, so the published source alone cannot confirm that the pages were successfully saved or rendered.
   - Open `powerbi/Customer Churn Early-Warning System.pbix` in Power BI Desktop, then run:
     ```powershell
     powershell -ExecutionPolicy Bypass -File scripts\build_powerbi_model.ps1
     ```
     and verify table relationships, data refresh, and page rendering before pressing **`Ctrl+S`** to persist the newly added semantic model tables (`ChurnPredictions`, `FeatureImportance`, `ModelExperiments`, `FeatureRegistry`, `DriverRankSlot`, `CalibrationDeciles`, `ConfusionMatrixTable`, `ThresholdPolicyTable`, `DataQualityChecks`), relationships, calculated columns, and 51 German DAX measures inside the `.pbix` binary.
2. **Re-running the Python ML + Power BI Asset Pipeline**:
   - `.\.venv\Scripts\python.exe -m src.pipeline.run_pipeline --skip-etl`
   - `.\.venv\Scripts\python.exe scripts\prepare_powerbi_outputs.py`
   - `.\.venv\Scripts\python.exe scripts\build_powerbi_report_pages.py`
3. Set real retention costs and capacity in `src/config.py` (`COST_*`, `OPERATING_CAPACITY`, `RISK_TIER_CAPACITY`) if you want different thresholds.
