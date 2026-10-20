"""Behavioural hypotheses for engineered features (Phase 13).

Every feature uses only the current and previous months of the customer's own
timeline (SQL window frames end at CURRENT ROW), so it is known at the end of T.
"""

ENGINEERED_FEATURES = {
    "AvgTransactionCount_3M": "Baseline activity level; a drop of current activity below it signals disengagement.",
    "AvgTransactionCount_6M": "Longer baseline that is less sensitive to a single quiet month.",
    "AvgAmount_3M": "Average monthly spend over the last 3 months; falling spend can precede inactivity.",
    "AvgAmount_6M": "Longer spend baseline.",
    "ActiveMonths_3M": "Months with any activity in the last 3: intermittent users are likelier to skip a month.",
    "ActiveMonths_6M": "Months with any activity in the last 6: habit strength.",
    "TransactionCountStdDev_3M": "Volatile activity indicates irregular usage and higher gap risk.",
    "AmountStdDev_3M": "Volatile spend indicates irregular usage.",
    "TransactionTypeDiversity_3M": "Customers using fewer transaction types are less embedded in the product.",
    "Recent3MPaymentShare": "Mix shift toward/away from bill payments (a sticky use case).",
    "Recent3MTransferShare": "Mix shift in transfers.",
    "Recent3MWithdrawalShare": "Mix shift toward cash withdrawals may signal reduced app usage.",
    "Recent3MDepositShare": "Mix shift in deposits (money still entering the account).",
}

NULL_INDICATORS = {
    "TransactionCountChangePct": "TransactionCountChangePct_IsNull",
    "TotalAmountChangePct": "TotalAmountChangePct_IsNull",
    "TransactionCount_3M_ChangePct": "TransactionCount_3M_ChangePct_IsNull",
    "TotalAmount_3M_ChangePct": "TotalAmount_3M_ChangePct_IsNull",
}

TRANSACTION_TYPES = ["Transfer", "Payment", "Withdrawal", "Deposit"]

