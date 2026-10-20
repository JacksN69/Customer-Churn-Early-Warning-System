CREATE TEMP TABLE expected_features AS
WITH extras AS (
    SELECT customer_id, DATE_TRUNC('month',date)::DATE AS Month,
           MIN(date) AS FirstTransactionDate,
           COALESCE(ROUND(AVG(amount),0),0) AS AverageAmount,
           COALESCE(MAX(amount),0) AS MaxAmount,
           MAX(date) AS LastTransactionDate,
           COUNT(DISTINCT date) AS ActiveDays,
           COUNT(*) FILTER (WHERE ISODOW(date) IN (6,7)) AS WeekendTransactionCount
    FROM tx GROUP BY 1,2
),
base AS (
    SELECT m.*, e.FirstTransactionDate, e.LastTransactionDate,
           COALESCE(e.AverageAmount,0) AS AverageAmount,
           COALESCE(e.MaxAmount,0) AS MaxAmount,
           COALESCE(e.ActiveDays,0) AS ActiveDays,
           COALESCE(e.WeekendTransactionCount,0) AS WeekendTransactionCount
    FROM monthly_reference m LEFT JOIN extras e USING(customer_id,Month)
),
history AS (
    SELECT b.*,
           (ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY Month)-1) AS idx,
           MIN(Month) OVER (PARTITION BY customer_id) AS FirstObservedMonth,
           LAG(TransactionCount) OVER w AS PreviousTransactionCount,
           LAG(TotalAmount) OVER w AS PreviousTotalAmount,
           LAG(PaymentCount) OVER w AS PreviousPaymentCount,
           LAG(WithdrawalCount) OVER w AS PreviousWithdrawalCount,
           LAG(DepositCount) OVER w AS PreviousDepositCount,
           LAG(TransferCount) OVER w AS PreviousTransferCount,
           LEAD(TransactionCount,1) OVER w AS NextTx,
           LEAD(TransactionCount,2) OVER w AS Next2Tx,
           LEAD(TransactionCount,3) OVER w AS Next3Tx,
           SUM(TransactionCount) OVER (
             PARTITION BY customer_id ORDER BY Month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
           ) AS TransactionCount_Recent3M,
           SUM(TransactionCount) OVER (
             PARTITION BY customer_id ORDER BY Month ROWS BETWEEN 5 PRECEDING AND 3 PRECEDING
           ) AS raw_Previous3M,
           SUM(TotalAmount) OVER (
             PARTITION BY customer_id ORDER BY Month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
           ) AS TotalAmount_Recent3M,
           SUM(TotalAmount) OVER (
             PARTITION BY customer_id ORDER BY Month ROWS BETWEEN 5 PRECEDING AND 3 PRECEDING
           ) AS raw_PreviousAmount3M,
           MAX(LastTransactionDate) OVER (
             PARTITION BY customer_id ORDER BY Month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS KnownLastTx,
           0 AS placeholder
    FROM base b
    WINDOW w AS (PARTITION BY customer_id ORDER BY Month)
),
with_streak AS (
    SELECT h.* EXCLUDE (placeholder),
           MAX(CASE WHEN TransactionCount > 0 THEN idx ELSE NULL END)
             OVER (PARTITION BY customer_id ORDER BY Month
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS LastActiveIdx
    FROM history h
),
measures AS (
    SELECT s.*,
           CASE WHEN idx >= 5 THEN raw_Previous3M ELSE NULL END AS TransactionCount_Previous3M,
           CASE WHEN idx >= 5 THEN raw_PreviousAmount3M ELSE NULL END AS TotalAmount_Previous3M,
           CASE WHEN PreviousTransactionCount IS NULL THEN NULL
             ELSE TransactionCount - PreviousTransactionCount END AS TransactionCountChange,
           CASE WHEN PreviousTotalAmount IS NULL THEN NULL
             ELSE TotalAmount - PreviousTotalAmount END AS TotalAmountChange,
           CASE WHEN PreviousTransactionCount IS NULL THEN NULL
             WHEN PreviousTransactionCount = 0 AND TransactionCount = 0 THEN 0
             WHEN PreviousTransactionCount = 0 THEN NULL
             ELSE (TransactionCount - PreviousTransactionCount)::DOUBLE / PreviousTransactionCount END
             AS TransactionCountChangePct,
           CASE WHEN PreviousTotalAmount IS NULL THEN NULL
             WHEN PreviousTotalAmount = 0 AND TotalAmount = 0 THEN 0
             WHEN PreviousTotalAmount = 0 THEN NULL
             ELSE (TotalAmount - PreviousTotalAmount)::DOUBLE / PreviousTotalAmount END
             AS TotalAmountChangePct,
           CASE WHEN idx < 5 THEN NULL
             WHEN raw_Previous3M = 0 AND TransactionCount_Recent3M = 0 THEN 0
             WHEN raw_Previous3M = 0 THEN NULL
             ELSE (TransactionCount_Recent3M-raw_Previous3M)::DOUBLE/raw_Previous3M END
             AS TransactionCount_3M_ChangePct,
           CASE WHEN idx < 5 THEN NULL
             WHEN raw_PreviousAmount3M = 0 AND TotalAmount_Recent3M = 0 THEN 0
             WHEN raw_PreviousAmount3M = 0 THEN NULL
             ELSE (TotalAmount_Recent3M-raw_PreviousAmount3M)::DOUBLE/raw_PreviousAmount3M END
             AS TotalAmount_3M_ChangePct
    FROM with_streak s
)
SELECT
  customer_id, Month, FirstObservedMonth AS CustomerStartMonth,
  TransactionCount, TotalAmount, AverageAmount, MaxAmount,
  TransferCount,PaymentCount,WithdrawalCount,DepositCount,
  TransferAmount,PaymentAmount,WithdrawalAmount,DepositAmount,
  FirstTransactionDate,LastTransactionDate,ActiveDays,WeekendTransactionCount,
  TransactionCount::DOUBLE / DATE_DIFF('day', Month, Month + INTERVAL '1 month')
    AS TransactionsPerCalendarDay,
  CASE WHEN TransactionCount = 0 THEN 0 ELSE WeekendTransactionCount::DOUBLE / TransactionCount END
    AS WeekendTransactionRatio,
  DATE_DIFF('month',FirstObservedMonth, Month) AS ObservedTenureMonths,
  CASE WHEN TransactionCount = 0 THEN NULL
       WHEN TransferCount = GREATEST(TransferCount,PaymentCount,WithdrawalCount,DepositCount) THEN 'Transfer'
       WHEN PaymentCount = GREATEST(TransferCount,PaymentCount,WithdrawalCount,DepositCount) THEN 'Payment'
       WHEN WithdrawalCount = GREATEST(TransferCount,PaymentCount,WithdrawalCount,DepositCount) THEN 'Withdrawal'
       ELSE 'Deposit' END AS PreferredTransactionType,
  CASE WHEN TransactionCount=0 THEN 0 ELSE PaymentCount::DOUBLE/TransactionCount END AS PaymentShare,
  CASE WHEN TransactionCount=0 THEN 0 ELSE TransferCount::DOUBLE/TransactionCount END AS TransferShare,
  CASE WHEN TransactionCount=0 THEN 0 ELSE WithdrawalCount::DOUBLE/TransactionCount END AS WithdrawalShare,
  CASE WHEN TransactionCount=0 THEN 0 ELSE DepositCount::DOUBLE/TransactionCount END AS DepositShare,
  CASE WHEN TransactionCount=0 THEN 1 ELSE 0 END AS InactiveMonth,
  PreviousTransactionCount, PreviousTotalAmount,
  PreviousPaymentCount, PreviousWithdrawalCount, PreviousDepositCount, PreviousTransferCount,
  TransactionCountChange, TransactionCountChangePct,
  TotalAmountChange, TotalAmountChangePct,
  CASE WHEN TransactionCountChangePct <= -.5 THEN 1 ELSE 0 END AS ActivityDeclineFlag,
  CASE WHEN TransactionCount=0 THEN idx-COALESCE(LastActiveIdx,-1) ELSE 0 END
    AS ConsecutiveInactiveMonths,
  DATE_DIFF('day',KnownLastTx,LAST_DAY(Month)) AS DaysSinceLastTransaction,
  TransactionCount_Recent3M, TransactionCount_Previous3M, TransactionCount_3M_ChangePct,
  TotalAmount_Recent3M, TotalAmount_Previous3M, TotalAmount_3M_ChangePct,
  CASE WHEN TransactionCount_3M_ChangePct <= -.5 THEN 1 ELSE 0 END AS TransactionDecline50Pct,
  CASE WHEN TotalAmount_3M_ChangePct <= -.5 THEN 1 ELSE 0 END AS SpendingDecline50Pct,
  CASE WHEN NextTx IS NULL OR TransactionCount=0 THEN NULL
       WHEN NextTx=0 THEN 1 ELSE 0 END AS InactiveNextMonth,
  CASE WHEN Next3Tx IS NULL OR TransactionCount=0 THEN NULL
       WHEN NextTx+Next2Tx+Next3Tx=0 THEN 1 ELSE 0 END AS ExtendedInactivityNext3Months,
  CASE WHEN idx >= 5 THEN 1 ELSE 0 END AS Has6MonthHistory,
  CASE WHEN idx >= 5 AND TransactionCount>0 AND NextTx IS NOT NULL THEN 1 ELSE 0 END
    AS EligibleForTraining
FROM measures;
