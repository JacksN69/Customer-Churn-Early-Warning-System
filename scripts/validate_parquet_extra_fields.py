"""Validate seven additional feature columns against Power BI's DAX export."""
from pathlib import Path
import duckdb

ROOT=Path(__file__).resolve().parents[1]
CSV=ROOT/"reports"/"powerbi_additional_fields_private.csv"
PARQUET=ROOT/"data"/"processed"/"churn_features.parquet"
REPORT=ROOT/"reports"/"parquet_powerbi_additional_fields.md"
if not CSV.exists():raise FileNotFoundError(CSV)
db=duckdb.connect(":memory:")
csv=CSV.as_posix().replace("'","''")
parquet=PARQUET.as_posix().replace("'","''")
db.execute(f"CREATE VIEW d AS SELECT * FROM read_parquet('{parquet}')")
db.execute(f"CREATE VIEW raw AS SELECT * FROM read_csv_auto('{csv}',header=true)")
heads=[col[0] for col in db.execute("DESCRIBE raw").fetchall()]
columns=[c.rsplit('[',1)[-1].rstrip(']') for c in heads]
parts=[]
for a,b in zip(heads,columns):
    x='"'+a.replace('"','""')+'"'
    y='"'+b.replace('"','""')+'"'
    cast=("TRY_CAST("+x+" AS DATE)" if b in ("Month","CustomerStartMonth")
          else "CAST("+x+" AS VARCHAR)" if b=="customer_id" else x)
    parts.append(cast+" AS "+y)
db.execute("CREATE VIEW p AS SELECT "+", ".join(parts)+" FROM raw")
stats=db.execute("""SELECT (SELECT COUNT(*) FROM p),
(SELECT COUNT(*) FROM d),
(SELECT COUNT(*) FROM p LEFT JOIN d USING(customer_id,Month)
 WHERE d.customer_id IS NULL),
(SELECT COUNT(*) FROM d LEFT JOIN p USING(customer_id,Month)
 WHERE p.customer_id IS NULL)""").fetchone()
results=[]
for col in columns:
    if col in ("customer_id","Month"):continue
    if col=="AverageAmount":
        cond=f"ABS(CAST(p.{col} AS DOUBLE)-CAST(d.{col} AS DOUBLE)) > 0.01 OR ((p.{col} IS NULL) <> (d.{col} IS NULL))"
    else:
        cond=f"p.{col} IS DISTINCT FROM d.{col}"
    mismatches=db.execute(f"""SELECT COUNT(*) FROM p JOIN d USING(customer_id,Month)
          WHERE {cond}""").fetchone()[0]
    results.append((col,mismatches))
    print(col,mismatches)
ok=(stats[0]==stats[1] and stats[2]==0 and stats[3]==0 and all(n==0 for _,n in results))
content="\n".join(f"| {name} | {n:,} | {'PASS' if n==0 else 'FAIL'} |" for name,n in results)
REPORT.write_text(f"""# Additional Power BI versus Parquet field comparison

| Metric | Value |
|---|---:|
| Power BI rows | {stats[0]:,} |
| Parquet rows | {stats[1]:,} |
| Extra Power BI keys | {stats[2]:,} |
| Missing Power BI keys | {stats[3]:,} |

| Field | Mismatches | Result |
|---|---:|---|
{content}

## Verdict
**{'PASS' if ok else 'FAIL'}**
The seven fields were compared on all customer-month keys. AverageAmount
uses an absolute tolerance of 0.01; other data types use exact/null-safe comparison.
""",encoding="utf-8")
print(f"EXTRA_PARITY={ok}; report={REPORT}")
if not ok: raise SystemExit(1)
