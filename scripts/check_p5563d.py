"""p5563d code 0: `pase`, or a real frequency category?

p5563d is "Frecuencia Remesas de otros hogares o personas del extranjero" and INEI
declares "Rango: 1 - 8" (Diario ... Anual). The data holds code 0 in 5-10% of rows,
OUTSIDE the declared range and undocumented.

It is a FOLLOW-UP: you are only asked HOW OFTEN you receive a remittance if you
receive one at all. So the filter question decides it. If code 0 is `pase`:
  * code-0 rows must be people who did NOT report the remittance
  * codes 1-8 must be people who DID
That is the same behavioural proof that settled p1138 ('no cocinan' households skip
the cooking-fuel question) and p107a21 (only 'Si' opens the m2 follow-up).
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from perudata import dictionary as dic  # noqa: E402
from perudata import enaho  # noqa: E402

# the sibling that asks WHETHER, and the one that asks HOW MUCH
FILTER, AMOUNT = "p5563a", "p5563b"
print(f"p5563d (frequency) against {FILTER} (received?) and {AMOUNT} (amount)")
for y in (2004, 2006, 2015, 2020, 2025):
    try:
        d = enaho.load(y, "05", download_if_missing=False)
    except Exception:
        continue
    if "p5563d" not in d.columns:
        continue
    freq = pd.to_numeric(d["p5563d"], errors="coerce")
    print(f"\n   {y}: p5563d label = {dic.value_labels('p5563d', y, '05')}")
    for sib in (FILTER, AMOUNT):
        if sib not in d.columns:
            continue
        s = pd.to_numeric(d[sib], errors="coerce")
        z = freq == 0
        nz = freq.between(1, 8)
        # does the sibling get answered by code-0 rows, or only by codes 1-8?
        print(f"      {sib}: answered by code-0 rows "
              f"{100 * s[z].notna().mean():5.1f}% (n={int(z.sum()):,}) | "
              f"by codes 1-8 {100 * s[nz].notna().mean():5.1f}% (n={int(nz.sum()):,})")
