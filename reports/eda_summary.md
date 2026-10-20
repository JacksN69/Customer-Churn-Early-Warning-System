# EDA summary (Phase 11)

Source: `notebooks/01_eda.ipynb` (executed; charts and tables stored in the notebook).
Population: 224,360 labelled customer-months (T = Jun–Nov 2023), 48,674 customers.
Everything below is a descriptive association, **not** a causal claim. The target is
next-month transactional inactivity, not confirmed account closure.

## Target distribution
- Overall `InactiveNextMonth = 1`: 39,039 of 224,360 (17.40%).
- By observation month: Jun 14.82%, Jul 16.69%, Aug 17.97%, Sep 17.25%, Oct 18.26%, Nov 18.86%
  (range 4.0 pp, a gradual rise rather than a sharp calendar jump).

## Most inactive-next-month rows are transient gaps
- Of rows with `InactiveNextMonth = 1` and T+2 observed, **72.6%** transact again at T+2.
- `ExtendedInactivityNext3Months = 1` occurs in only 4,723 of 350,870 observed rows (1.3%).
- Implication: the model predicts "a skipped month", which is mostly a low-frequency-usage pattern, not
  departure. Dashboards should say "inactivity risk", not "churn".

## Behavioural comparison (inactive next month vs active next month)
| Feature | Median active-next | Median inactive-next | Standardised difference |
|---|---:|---:|---:|
| TransactionCount (month T) | 2 | 2 | -0.14 |
| ActiveDays | 2 | 2 | -0.65 |
| DaysSinceLastTransaction | 6 | 10 | +0.35 |
| TransactionCount_3M_ChangePct (mean) | 0.28 | 0.47 | +0.17 |
| TotalAmount_3M_ChangePct (mean) | 0.56 | 0.93 | +0.14 |

- The groups are separated mainly by **how active they chronically are**: customers who go inactive averaged
  ~1.4 transactions per month for the six months up to T (vs ~7.8 for others) and show **no decline before
  the event** (1.41, 1.36, 1.37, 1.37, 1.37, then 1.85 in T).
- The change-percentage features are *higher* for the inactive group (low bases make percentages swing),
  so the "visible deterioration before inactivity" hypothesis is **not supported** by these data. The
  Customer 360 page should not promise to show deterioration.

## Transaction composition
- Mean shares differ by less than 0.4 pp between groups (Payment 30.6% vs 30.9%, Transfer 45.1% vs 44.9%,
  Withdrawal 14.7% vs 14.3%, Deposit 9.6% vs 9.8%): customers approaching inactivity do not change their
  mix in a material way.
- By `PreferredTransactionType` in month T the next-month inactivity rate is Deposit 23.3%,
  Withdrawal 20.8%, Payment 18.6%, Transfer 16.1%.

## Recency
- Rate rises monotonically with `DaysSinceLastTransaction`: 8.2% (transacted on the last day), 12.8% (1–3 days),
  16.6% (4–7), 20.5% (8–14), 23.3% (15–21), 24.9% (22–31). Recency is a clear, interpretable signal.

## Customer characteristics (segmentation only)
Spread between the highest and lowest group (groups with at least 500 customer-months):
age 0.7 pp, income 0.2 pp, acquisition channel 0.5 pp, education 0.2 pp, gender 0.4 pp,
occupation 1.9 pp, location 3.1 pp (largest rate: Neiva, Huila at 19.3% on only 2,237 rows).
Profile attributes give almost no segmentation signal. `age` has only six distinct values
(29, 30, 44, 45, 59, 60), suggesting synthetic or banded data.

## Data note: `ObservedTenureMonths`
About 80% of customers first appear in January 2023, so tenure equals the calendar-month index for most
rows, and the test and scoring months contain tenure values never seen in training (training max 8, test 10,
December 11). The feature is excluded from modelling (registry policy `EXCLUDE`).
