# Profile missingness and historical timing audit

Source: original \`customer_data.csv\` with 48,723 customer records.

| Check | Count |
|---|---:|
| Credit ratio blank/null | 18,263 |
| Requests blank/null | 16,115 |
| Complaint topics blank/null | 24,346 |
| Credit card = FALSE but ratio present | 0 |
| Credit card = TRUE but ratio missing | 0 |

| Credit card | Customers | Ratio missing | Ratio present |
|---|---:|---:|---:|
| False | 18,263 | 18,263 | 0 |
| True | 30,460 | 0 | 30,460 |

## Missing-value interpretation

- Credit utilization ratio is **not applicable** if there is no credit card;
  its numeric value must remain NULL, **not 0**.
- Blank \`feature_requests\` and \`complaint_topics\` mean **Not recorded**,
  not confirmed none/zero. Raw NULLs are preserved.
- Power BI should display separate category labels while numeric analyses
  continue to exclude missing utilization from the denominator.

## Historical feature availability

- Raw \`transactions_data.csv\` has transaction dates; transaction-derived
  features use data through the end of observation month T.
- \`customer_data.csv\` is one undated snapshot per customer. It contains
  \`last_survey_date\`, spanning 2023-01-01–2023-12-31 across 365 distinct days.
  This may date a last survey, but it does not timestamp product ownership,
  app usage, support metrics, credit utilization, or the entire satisfaction
  record. It does not establish as-of snapshots for arbitrary months.
- Vendor/transaction summary fields in customer data (first_tx/last_tx etc.)
  do not establish acquisition timestamps for other fields.
- Hence none of these snapshot fields can be defensibly backfilled to
  month T; keep them out of historical training. No imputed recording dates.
