# COFINFAD Raw Transaction Data Quality Report

## Source

`transactions_data.csv`

This report audits the raw transaction source before monthly
aggregation, feature engineering, or machine-learning modeling.

---

## 1. Dataset Summary

| Metric | Result |
|---|---:|
| Rows | 3,159,157 |
| Unique customers | 48,723 |
| First transaction date | 2023-01-04 |
| Last transaction date | 2023-12-29 |
| Null customer IDs | 0 |
| Null dates | 0 |
| Null amounts | 0 |
| Null transaction types | 0 |

---

## 2. Transaction Types

| Type | Rows |
|---|---:|
| Transfer | 1,433,963 |
| Payment | 970,548 |
| Withdrawal | 456,577 |
| Deposit | 298,069 |

Expected values:

- Transfer
- Payment
- Withdrawal
- Deposit

---

## 3. Unexpected Transaction Types

| Type | Rows |
|---|---:|
| None | 0 |

---

## 4. Transaction Amount Validation

| Metric | Result |
|---|---:|
| Minimum amount | 36,400.00 |
| Maximum amount | 689,739,900.00 |
| Average amount | 3,970,948.44 |
| Negative amounts | 0 |
| Zero amounts | 0 |
| Non-positive amounts | 0 |

Amounts are expected to be expressed in Colombian Pesos (COP).

---

## 5. Exact Duplicate Check

Exact duplicate definition:

`customer_id + date + amount + type`

| Metric | Result |
|---|---:|
| Duplicate groups | 102 |
| Additional duplicate rows | 102 |

Important:

Because this dataset does not contain a unique transaction ID,
identical rows are not automatically removed. Two identical rows
could potentially represent legitimate separate transactions.

---

## 6. Initial Data-Quality Status

Raw rows: **3,159,157**

Unique customers: **48,723**

Date range: **2023-01-04 → 2023-12-29**

The results above should be reviewed before proceeding to
customer-month aggregation.
