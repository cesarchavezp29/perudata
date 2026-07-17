"""WHY were the ocu500=0 people not interviewed for employment?

Established: they answer NO module-05 question at all -- p501, the module's first
question, is 0.0% answered for them and 100.0% for codes 1-4, in every year. So
ocu500=0 is "no employment interview", not a PEA category.

Now the mechanism, because a label should say WHAT it is, not just what it is not.
Cross the roster (module 02): are they non-habitual residents (p204==2), absent
(p205==1), or something else? The roster is where INEI records who was present.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from perudata import harmonize  # noqa: E402
from perudata import enaho  # noqa: E402

PK = ["conglome", "vivienda", "hogar", "codperso"]

for y in (2004, 2012, 2020, 2025):
    try:
        m5 = enaho.load(y, "05", download_if_missing=False)
        m2 = enaho.load(y, "02", download_if_missing=False)
    except Exception:
        continue
    m5 = harmonize.normalize_keys(m5)
    m2 = harmonize.normalize_keys(m2)
    cols = [c for c in ("p204", "p205", "p206", "p208a") if c in m2.columns]
    j = m5[PK + ["ocu500"]].merge(m2[PK + cols], on=PK, how="left")
    v = pd.to_numeric(j["ocu500"], errors="coerce")
    z, nz = v == 0, v.between(1, 4)
    print(f"--- {y}: {int(z.sum()):,} rows at ocu500=0")
    for c in cols:
        s = pd.to_numeric(j[c], errors="coerce")
        if c == "p208a":
            print(f"      {c}: code0 median {s[z].median()} | codes1-4 median "
                  f"{s[nz].median()}")
            continue
        d0 = s[z].value_counts(dropna=False, normalize=True).head(3).round(3).to_dict()
        d1 = s[nz].value_counts(dropna=False, normalize=True).head(3).round(3).to_dict()
        print(f"      {c}: code0 {d0}")
        print(f"      {' ' * len(c)}  codes1-4 {d1}")
