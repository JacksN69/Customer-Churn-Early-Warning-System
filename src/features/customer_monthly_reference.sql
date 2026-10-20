CREATE TEMP TABLE monthly_reference AS
    WITH actual AS (
        SELECT
            customer_id,
            DATE_TRUNC('month', date)::DATE AS Month,
            COUNT(*)::BIGINT AS TransactionCount,
            SUM(amount) AS TotalAmount,
            COUNT(*) FILTER (WHERE type = 'Transfer') AS TransferCount,
            COUNT(*) FILTER (WHERE type = 'Payment') AS PaymentCount,
            COUNT(*) FILTER (WHERE type = 'Withdrawal') AS WithdrawalCount,
            COUNT(*) FILTER (WHERE type = 'Deposit') AS DepositCount,
            SUM(CASE WHEN type = 'Transfer' THEN amount ELSE 0 END) AS TransferAmount,
            SUM(CASE WHEN type = 'Payment' THEN amount ELSE 0 END) AS PaymentAmount,
            SUM(CASE WHEN type = 'Withdrawal' THEN amount ELSE 0 END) AS WithdrawalAmount,
            SUM(CASE WHEN type = 'Deposit' THEN amount ELSE 0 END) AS DepositAmount
        FROM tx
        GROUP BY customer_id, Month
    ),
    starts AS (
        SELECT customer_id, MIN(Month) AS first_month
        FROM actual GROUP BY customer_id
    ),
    last_month AS (
        SELECT MAX(Month) AS final_month FROM actual
    ),
    scaffold AS (
        SELECT s.customer_id, g.Month::DATE AS Month
        FROM starts s
        CROSS JOIN last_month l
        CROSS JOIN LATERAL
          GENERATE_SERIES(s.first_month, l.final_month, INTERVAL '1 month') AS g(Month)
    )
    SELECT
        s.customer_id,
        s.Month,
        COALESCE(a.TransactionCount, 0)::BIGINT AS TransactionCount,
        COALESCE(a.TotalAmount, 0)::DECIMAL(38,2) AS TotalAmount,
        COALESCE(a.TransferCount, 0)::BIGINT AS TransferCount,
        COALESCE(a.PaymentCount, 0)::BIGINT AS PaymentCount,
        COALESCE(a.WithdrawalCount, 0)::BIGINT AS WithdrawalCount,
        COALESCE(a.DepositCount, 0)::BIGINT AS DepositCount,
        COALESCE(a.TransferAmount, 0)::DECIMAL(38,2) AS TransferAmount,
        COALESCE(a.PaymentAmount, 0)::DECIMAL(38,2) AS PaymentAmount,
        COALESCE(a.WithdrawalAmount, 0)::DECIMAL(38,2) AS WithdrawalAmount,
        COALESCE(a.DepositAmount, 0)::DECIMAL(38,2) AS DepositAmount
    FROM scaffold s
    LEFT JOIN actual a USING (customer_id, Month);
