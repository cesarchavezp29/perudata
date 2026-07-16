"""Two singletons that need a real proof, not a pattern.

p1138 in 2007: the data holds 0 and EIGHT (1,013 rows). Every other year holds 0
  and ONE (~700-900 rows). The dictionary says "1 No cocinan, Rango : 0 - 1", and
  code 8 appears in NO other year. Hypothesis: this is the same battery-position
  bug as p114x -- p1138 is the 8th slot, so 2007 wrote 8 instead of 1.
  TEST: does code 8 in 2007 behave exactly like code 1 elsewhere? "No cocinan"
  households must NOT answer the cooking-fuel question (p113a).

panel in 2004: 6,880 rows at code 0, versus 8 in 2005 and none after. Label is
  {1: si, 2: no} in every year, dictionary says "Rango : 1 - 2". Code 0 is OUTSIDE
  the declared range. Is it a category, or the un-asked residue of a panel that did
  not exist yet in the first survey year?
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from perudata import enaho  # noqa: E402

print("=" * 78)
print("p1138 ('no cocinan'): does 2007's code 8 behave like code 1 elsewhere?")
print("A 'no cocinan' household must SKIP the cooking-fuel question p113a.")
print(f"{'year':<6}{'code':>6}{'rows':>8}{'p113a answered':>16}")
for y in (2007, 2008, 2009, 2010, 2011):
    d = enaho.load(y, "01", download_if_missing=False)
    if "p1138" not in d.columns or "p113a" not in d.columns:
        continue
    v = pd.to_numeric(d["p1138"], errors="coerce")
    fuel = pd.to_numeric(d["p113a"], errors="coerce")
    for code in sorted({int(x) for x in v.dropna().unique()}):
        if code == 0:
            continue
        sel = v == code
        # "no cocinan" -> the fuel question is not applicable
        answered = 100 * (fuel[sel].notna() & (fuel[sel] > 0)).mean()
        print(f"{y:<6}{code:>6}{int(sel.sum()):>8}{answered:>15.1f}%")

print()
print("=" * 78)
print("panel: code 0 in 2004 (6,880 rows) vs 2005 (8) vs later (none)")
for y in (2004, 2005, 2006, 2010):
    d = enaho.load(y, "01", download_if_missing=False)
    if "panel" not in d.columns:
        continue
    v = pd.to_numeric(d["panel"], errors="coerce")
    print(f"   {y}: {v.value_counts(dropna=False).head(4).to_dict()} "
          f"| total rows {len(v):,}")
print()
print("2004 is ENAHO's first year under this design: there IS no 'last year' to")
print("have been interviewed in, which is exactly what an out-of-range residue")
print("that vanishes by 2005 looks like.")
