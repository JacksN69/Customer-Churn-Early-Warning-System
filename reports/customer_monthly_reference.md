# Independent Customer-Month Reference Audit

Generated from unmodified `data/raw/transactions_data.csv` in DuckDB.

**Important:** This is an independent reference; it does **not** establish
Power Query / PBIX equivalence until exported results are compared.

## Counts

| Metric | Value |
|---|---:|
| Raw transaction rows | 3,159,157 |
| Unique raw customers | 48,723 |
| Customer-month rows | 569,706 |
| Active customer-months | 467,721 |
| Zero-transaction customer-months | 101,985 |
| Duplicate customer-month keys | 0 |
| Reference eligible rows | 224,360 |
| Reference positive labels | 39,039 |
| Reference positive rate | 17.40% |

## Invariants

| Check | Result |
|---|---|
| customer counts reconcile | PASS |
| transaction counts reconcile | PASS |
| transaction amounts reconcile | PASS |
| transaction-type counts reconcile | PASS |
| transaction-type amounts reconcile | PASS |
| no monthly type-count mismatches | PASS |
| no monthly type-amount mismatches | PASS |
| unique customer/month keys | PASS |
| scaffold partitions all rows | PASS |

## Monthly aggregation

| Month | Customer-months | Active | Inactive | Transactions |
|---|---:|---:|---:|---:|
| 2023-01 | 38,139 | 38,139 | 0 | 245,641 |
| 2023-02 | 45,475 | 38,019 | 7,456 | 244,687 |
| 2023-03 | 47,865 | 39,404 | 8,461 | 271,531 |
| 2023-04 | 48,508 | 38,944 | 9,564 | 262,739 |
| 2023-05 | 48,668 | 39,423 | 9,245 | 271,948 |
| 2023-06 | 48,714 | 39,023 | 9,691 | 263,295 |
| 2023-07 | 48,722 | 39,513 | 9,209 | 272,652 |
| 2023-08 | 48,723 | 39,413 | 9,310 | 271,937 |
| 2023-09 | 48,723 | 38,992 | 9,731 | 263,439 |
| 2023-10 | 48,723 | 39,434 | 9,289 | 272,973 |
| 2023-11 | 48,723 | 38,885 | 9,838 | 263,127 |
| 2023-12 | 48,723 | 38,532 | 10,191 | 255,188 |

## Reference labels: active at T, inactive at T+1

| Month T | Eligible | Positives | Negatives | Positive rate |
|---|---:|---:|---:|---:|
| 2023-06 | 31,362 | 4,649 | 26,713 | 14.82% |
| 2023-07 | 37,114 | 6,196 | 30,918 | 16.69% |
| 2023-08 | 38,795 | 6,971 | 31,824 | 17.97% |
| 2023-09 | 38,822 | 6,698 | 32,124 | 17.25% |
| 2023-10 | 39,389 | 7,193 | 32,196 | 18.26% |
| 2023-11 | 38,878 | 7,332 | 31,546 | 18.86% |

## Next validation gate

Compare against the actual Power BI `CustomerMonthly` and
`ChurnFeatures` results, first by month, then sampled customers and
eventually full row/key reconciliation.

Never treat this reference audit alone as proof that Power Query is correct.
Do not deduplicate matching raw transactions without source confirmation.
