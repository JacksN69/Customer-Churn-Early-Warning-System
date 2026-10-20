"""Compare generated Parquet to all 44 previously verified columns from PBIX."""
from pathlib import Path
import duckdb

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"reports"/"powerbi_customer_month_actual.csv"
PARQUET=ROOT/"data"/"processed"/"churn_features.parquet"
REPORT=ROOT/"reports"/"parquet_powerbi_full_parity.md"
d=duckdb.connect(":memory:")
def sql_path(p):return p.as_posix().replace("'","''")
d.execute(f"CREATE VIEW src AS SELECT * FROM read_csv_auto('{sql_path(SOURCE)}',header=true,sample_size=-1)")
names=[x[0] for x in d.execute("DESCRIBE src").fetchall()]
columns=[x.rsplit("[",1)[-1].rstrip("]") for x in names]
def ident(x):return '"'+x.replace('"','""')+'"'
mapped=[]
for original,col in zip(names,columns):
    o=ident(original)
    if col=="Month" or col.endswith("Date"):
        expr=f"TRY_CAST({o} AS DATE)"
    elif col in ("customer_id","PreferredTransactionType"):
        expr=f"CAST({o} AS VARCHAR)"
    else:
        expr=o
    mapped.append(f"{expr} AS {ident(col)}")
d.execute("CREATE TEMP TABLE pbi AS SELECT "+", ".join(mapped)+" FROM src")
d.execute(f"CREATE VIEW parquet AS SELECT * FROM read_parquet('{sql_path(PARQUET)}')")
key_stats=d.execute("""SELECT
 (SELECT COUNT(*) FROM pbi),
 (SELECT COUNT(*) FROM parquet),
 (SELECT COUNT(*) FROM pbi a LEFT JOIN parquet b USING(customer_id,Month)
  WHERE b.customer_id IS NULL),
 (SELECT COUNT(*) FROM parquet b LEFT JOIN pbi a USING(customer_id,Month)
  WHERE a.customer_id IS NULL),
 (SELECT COUNT(*) FROM (SELECT customer_id,Month FROM parquet
  GROUP BY 1,2 HAVING COUNT(*)>1))
""").fetchone()
ratios={"TransactionsPerCalendarDay","WeekendTransactionRatio",
"PaymentShare","TransferShare","WithdrawalShare","DepositShare",
"TransactionCountChangePct","TotalAmountChangePct","TransactionCount_3M_ChangePct",
"TotalAmount_3M_ChangePct"}
money={"TotalAmount","TransferAmount","PaymentAmount","WithdrawalAmount","DepositAmount",
"PreviousTotalAmount","TotalAmountChange","TotalAmount_Recent3M","TotalAmount_Previous3M"}
results=[]
for col in columns:
    if col in ("customer_id","Month"): continue
    a="a."+ident(col)
    b="b."+ident(col)
    if col in ratios or col in money:
        atol="1e-8" if col in ratios else "0.01"
        cond=f"(({a} IS NULL) <> ({b} IS NULL)) OR ( {a} IS NOT NULL AND {b} IS NOT NULL AND ABS(CAST({a} AS DOUBLE)-CAST({b} AS DOUBLE))>{atol})"
    else:
        cond=f"{a} IS DISTINCT FROM {b}"
    n=d.execute(f"SELECT COUNT(*) FROM pbi a JOIN parquet b USING(customer_id,Month) WHERE {cond}").fetchone()[0]
    results.append((col,n))
    if n:print("MISMATCH",col,n)
pass_all=key_stats[0]==key_stats[1] and all(n==0 for n in key_stats[2:]) and not any(n for _,n in results)
row_lines="\n".join(f"| {name} | {n:,} | {'PASS' if n==0 else 'FAIL'} |" for name,n in results)
REPORT.write_text(f"""# Parquet migration regression against loaded Power BI

**{'PASS' if pass_all else 'FAIL'}** — comparison of original 44 behavior/target
fields on all customer-month keys against the saved Power BI DAX export.
The seven additional fields were separately checked in
`reports/parquet_powerbi_additional_fields.md`.

| Metric | Value |
|---|---:|
| Loaded Power BI rows | {key_stats[0]:,} |
| Parquet rows | {key_stats[1]:,} |
| Power BI keys missing in Parquet | {key_stats[2]:,} |
| Parquet keys missing in Power BI | {key_stats[3]:,} |
| Duplicate Parquet keys | {key_stats[4]:,} |
| Fields compared | {len(results)} |
| Fields with discrepancies | {sum(n>0 for _,n in results)} |

| Field | Mismatched rows | Result |
|---|---:|---|
{row_lines}

All comparisons are null-sensitive; amounts tolerate 0.01 and ratios 1e-8,
with exact comparison for other fields.
""",encoding="utf-8")
print(f"PARQUET_PARITY={pass_all}; fields={len(results)}; report={REPORT}")
if not pass_all:raise SystemExit(1)
