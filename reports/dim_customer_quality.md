# COFINFAD DimCustomer source quality audit

Raw CSV: `data/raw/customer_data.csv` (read only). Grain: expected one row per customer.

## Key quality / referential coverage

| Check | Value |
|---|---:|
| Customer source rows | 48,723 |
| Distinct nonblank customer IDs | 48,723 |
| Blank/null customer IDs | 0 |
| Duplicated customer-ID groups | 0 |
| Additional customer-ID rows | 0 |
| Duplicated IDs with nonidentical full rows | 0 |
| Unique transaction customers | 48,723 |
| Transaction customer IDs matched to DimCustomer raw IDs | 48,723 |
| Transaction customer IDs missing in customer source | 0 |
| Customer IDs absent from transactions | 0 |
| Source column count | 54 |

## Demographic and date checks
- Age outside [18,110]: 0
- Non-numeric nonblank ages: 0
- Earliest/latest observed survey dates: 2023-01-01, 2023-12-31
- Survey dates after Dec 2023: 0
- A survey date column is **not** proof that the rest of the customer snapshot was known at observation month T.

## Numeric parsing

| Field | Nonblank invalid numeric strings |
|---|---:|
| age | 0 |
| household_size | 0 |
| satisfaction_score | 0 |
| nps_score | 0 |
| support_tickets_count | 0 |
| app_logins_frequency | 0 |

## Column completeness and distinct counts

| Column | Populated | Missing/blank | Distinct |
|---|---:|---:|---:|
| customer_id | 48,723 | 0 (0.0%) | 48,723 |
| age | 48,723 | 0 (0.0%) | 6 |
| gender | 48,723 | 0 (0.0%) | 3 |
| location | 48,723 | 0 (0.0%) | 18 |
| income_bracket | 48,723 | 0 (0.0%) | 4 |
| occupation | 48,723 | 0 (0.0%) | 35 |
| education_level | 48,723 | 0 (0.0%) | 4 |
| marital_status | 48,723 | 0 (0.0%) | 4 |
| household_size | 48,723 | 0 (0.0%) | 13 |
| acquisition_channel | 48,723 | 0 (0.0%) | 4 |
| customer_segment | 48,723 | 0 (0.0%) | 4 |
| savings_account | 48,723 | 0 (0.0%) | 2 |
| credit_card | 48,723 | 0 (0.0%) | 2 |
| personal_loan | 48,723 | 0 (0.0%) | 2 |
| investment_account | 48,723 | 0 (0.0%) | 2 |
| insurance_product | 48,723 | 0 (0.0%) | 2 |
| active_products | 48,723 | 0 (0.0%) | 5 |
| app_logins_frequency | 48,723 | 0 (0.0%) | 27 |
| feature_usage_diversity | 48,723 | 0 (0.0%) | 11 |
| bill_payment_user | 48,723 | 0 (0.0%) | 2 |
| auto_savings_enabled | 48,723 | 0 (0.0%) | 2 |
| credit_utilization_ratio | 30,460 | 18,263 (37.5%) | 30,460 |
| international_transactions | 48,723 | 0 (0.0%) | 7 |
| failed_transactions | 48,723 | 0 (0.0%) | 5 |
| tx_count | 48,723 | 0 (0.0%) | 988 |
| avg_tx_value | 48,723 | 0 (0.0%) | 48,577 |
| total_tx_volume | 48,723 | 0 (0.0%) | 48,277 |
| first_tx | 48,723 | 0 (0.0%) | 180 |
| last_tx | 48,723 | 0 (0.0%) | 174 |
| base_satisfaction | 48,723 | 0 (0.0%) | 48,723 |
| tx_satisfaction | 48,723 | 0 (0.0%) | 191 |
| product_satisfaction | 48,723 | 0 (0.0%) | 6 |
| satisfaction_score | 48,723 | 0 (0.0%) | 5 |
| nps_score | 48,723 | 0 (0.0%) | 99 |
| last_survey_date | 48,723 | 0 (0.0%) | 365 |
| support_tickets_count | 48,723 | 0 (0.0%) | 8 |
| resolved_tickets_ratio | 48,723 | 0 (0.0%) | 16 |
| app_store_rating | 48,723 | 0 (0.0%) | 7 |
| feedback_sentiment | 48,723 | 0 (0.0%) | 3 |
| feature_requests | 32,608 | 16,115 (33.1%) | 25 |
| complaint_topics | 24,377 | 24,346 (50.0%) | 5 |
| clv_segment | 48,723 | 0 (0.0%) | 4 |
| monthly_transaction_count | 48,723 | 0 (0.0%) | 1,133 |
| average_transaction_value | 48,723 | 0 (0.0%) | 48,577 |
| total_transaction_volume | 48,723 | 0 (0.0%) | 48,277 |
| transaction_frequency | 48,723 | 0 (0.0%) | 6,365 |
| last_transaction_date | 48,723 | 0 (0.0%) | 174 |
| preferred_transaction_type | 48,723 | 0 (0.0%) | 4 |
| first_transaction_date | 48,723 | 0 (0.0%) | 180 |
| weekend_transaction_ratio | 48,723 | 0 (0.0%) | 2,864 |
| avg_daily_transactions | 48,723 | 0 (0.0%) | 6,365 |
| customer_tenure | 48,723 | 0 (0.0%) | 180 |
| churn_probability | 48,723 | 0 (0.0%) | 1,977 |
| customer_lifetime_value | 48,723 | 0 (0.0%) | 48,723 |

## Feature policy
- Exclude all transaction-derived/customer-provider summary fields in DimCustomer ML: tx_count, avg_tx_value, total_tx_volume, first_tx, last_tx, monthly_transaction_count, average_transaction_value, total_transaction_volume, transaction_frequency, last_transaction_date, preferred_transaction_type, first_transaction_date, weekend_transaction_ratio, avg_daily_transactions, customer_tenure, churn_probability.
- Exclude vendor churn_probability from both target and ML features.
- Not historically defensible without dated source snapshots (do **not** use in historical training): customer_segment, savings_account, credit_card, personal_loan, investment_account, insurance_product, active_products, app_logins_frequency, feature_usage_diversity, bill_payment_user, auto_savings_enabled, credit_utilization_ratio, international_transactions, failed_transactions, base_satisfaction, tx_satisfaction, product_satisfaction, satisfaction_score, nps_score, last_survey_date, support_tickets_count, resolved_tickets_ratio, app_store_rating, feedback_sentiment, feature_requests, complaint_topics, clv_segment, customer_lifetime_value.
- Treat age/profile attributes as potentially static descriptive data only; birth-date/collection timestamp must be established before using age or location in historical ML.
- Raw transaction activity remains the source of truth.

## Rules
- Never call `Table.Distinct` without profiling duplicate IDs and conflicts.
- Preserve customer raw data unchanged. Avoid exporting customer-level PII in this report.
