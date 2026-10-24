# Reproducing and validating the project

This repository publishes source code, metadata and aggregate reports. It does **not** include the customer CSVs, generated Parquet datasets, trained models or a PBIX binary. The published metrics are historical results of a local execution; they are not independently reproducible from this checkout alone.

## Local Python checks

With Python and the pinned dependencies installed:

```powershell
python -m pip install -r requirements.txt
python -m pytest tests -ra
```

The small synthetic SQL feature tests and metric tests are intended to run without private inputs. Tests marked as requiring data are skipped until the original CSVs and derived Parquet files are available. A run with skips is not equivalent to a successful end-to-end pipeline verification. Report both passed and skipped counts.

## Private-data pipeline

Place the original files in `data/raw/` (do not commit them), then run:

```powershell
python -m src.pipeline.run_pipeline
```

Compare the outputs with `reports/pipeline_validation.md`, `reports/feature_validation.md`, and `reports/model_evaluation.md`. Investigate differences instead of adjusting thresholds or test assertions to force previously reported numbers.

## Power BI

The public repository includes `powerbi/model.bim`, DAX definitions, Power Query templates, and scripts for constructing a six-page report, but no PBIX binary. On Windows, provide the original local PBIX, private datasets and generated outputs. Refresh data sources using local paths and close unrelated Power BI Desktop sessions before connecting to the local Analysis Services instance.

The model-update script takes optional location arguments:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_powerbi_model.ps1
# Custom Power BI Desktop binary location:
powershell -ExecutionPolicy Bypass -File scripts\build_powerbi_model.ps1 -PowerBIBin 'D:\Apps\PowerBI\bin'
```

The script now aborts if Power BI Desktop is already running without a usable model; it does not forcibly close processes or restore a PBIX backup in that situation. Confirm the correct report is open before running it. Save, close, reopen, and verify page contents and DAX measures before publishing.

## Provenance

Keep original development records intact. Generated reports, phase labels and previous experimental approaches are useful to explain decisions, but should be clearly distinguished from the final model. No claim about the percentage of code authored by AI or a human can be established from the public source alone.
