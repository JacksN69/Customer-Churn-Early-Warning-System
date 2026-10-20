# Reproducible DuckDB / Parquet ETL validation

Built from original read-only COFINFAD raw CSVs using SQL located in
`src/features/`. The vetted 44-column behavioral semantics were independently
reconciled against the saved Power BI model before this migration.

| Metric | Value |
|---|---:|
| Raw transactions | 3,159,157 |
| Unique transaction customers | 48,723 |
| Customer-month records | 569,706 |
| Zero-transaction months | 101,985 |
| Eligible records | 224,360 |
| Primary positive labels | 39,039 |
| Dimension customer rows | 48,723 |
| Dimension transaction orphans | 0 |
| Feature columns in churn_features.parquet | 53 |
| Feature columns in customer_monthly.parquet | 39 |

## Gates
| Gate | Result |
|---|---|
| transaction count | PASS |
| transaction amount | PASS |
| customer identifiers | PASS |
| customer-month keys unique | PASS |
| no leaked primary target | PASS |
| expected 2023 snapshot row count | PASS |
| expected eligible rows | PASS |
| expected positive labels | PASS |

## Parquet readback
| File | Actual rows | Result |
|---|---:|---|
| customer_monthly.parquet | 569,706 | PASS |
| churn_features.parquet | 569,706 | PASS |
| dim_customer.parquet | 48,723 | PASS |

## Scope and privacy
- Raw CSVs and original PBIX were not altered by this script.
- Customer snapshots (app usage, satisfaction, NPS, product ownership, support,
  CLV etc.) are excluded from historical ML until a point-in-time source is proved.
- Do not use `churn_probability` as a feature or target.
- DimCustomer Parquet contains customer-level records and must remain private.
- Model label means next-month **transactional inactivity**, not account closure.
