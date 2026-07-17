"""Triage module 05's last 55: which are patterns, and which are single-row noise?

p5581a's code 0 is ONE row in 84,853. That is the estrsocial shape (a code the
dictionary omits) at 1/13000th the mass — and one observation cannot establish a
meaning. estrsocial was certifiable because 12,952 records made a deterministic
statement possible (code 6 iff estrato rural, zero mismatches). One row makes no
statement at all.

So: for each unresolved code, HOW MANY ROWS carry it? That separates
  * a real pattern worth resolving (thousands of rows, a consistent story)
  * single-row noise, which is likely a data-entry or encoding artifact and must be
    declined, exactly like p207's -126 int8 overflow
"""
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from perudata import enaho  # noqa: E402

ROOT = Path(__file__).parents[1]
res = pd.read_csv(ROOT / "scripts" / "recode_filter_results.csv", dtype=str)
bad = res[res.verdict == "UNRESOLVED_MAPPING"]

frames = {}
rows = []
for _, r in bad.iterrows():
    col = r["column"]
    m = re.findall(r"(\d{4}): \[([\d, ]+)\]", str(r["reason"]))
    for y_s, codes_s in m:
        y = int(y_s)
        if y not in frames:
            try:
                frames[y] = enaho.load(y, "05", download_if_missing=False)
            except Exception:
                frames[y] = None
        f = frames[y]
        if f is None or col not in f.columns:
            continue
        v = pd.to_numeric(f[col], errors="coerce")
        for c in [int(x) for x in codes_s.split(",") if x.strip()]:
            n = int((v == c).sum())
            rows.append({"column": col, "year": y, "code": c, "rows": n,
                         "total": len(v),
                         "share_pct": round(100 * n / len(v), 4)})

t = pd.DataFrame(rows)
if t.empty:
    print("nothing to triage")
    raise SystemExit
t.to_csv(ROOT / "scripts" / "m05_residue_mass.csv", index=False)
tiny = t[t["rows"] <= 5]
print(f"unresolved (column, year, code) triples: {len(t)}")
print(f"  carrying <= 5 ROWS  (noise, decline): {len(tiny)}")
print(f"  carrying  > 5 rows  (a real pattern): {len(t) - len(tiny)}")
print()
print("the single-row / near-zero ones:")
print(tiny.sort_values("rows").head(12).to_string(index=False))
print()
print("the ones with real mass:")
print(t[t["rows"] > 5].sort_values("rows", ascending=False).head(10)
      .to_string(index=False))
