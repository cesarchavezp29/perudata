"""Is p1142 code 1 mobile-phone ownership in EVERY year?

The 2006/2007 .dta labels say {0: pase, 2: celular} -- but the data contains NO
code 2. It holds 0 and 1, the official dictionary says "1 Celular, Rango: 0-1",
and by 2008 the .dta label is corrected to {0: pase, 1: celular}. So the embedded
label points at a code that does not exist.

If code 1 is ownership in every year, its weighted share must form a smooth ramp
across 2006/2007 -- a mislabel does not bend the data, only its description.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from perudata import dictionary as dic  # noqa: E402
from perudata import enaho  # noqa: E402

print(f"{'year':<6}{'code 1 share':>14}{'code 2 rows':>13}   .dta label")
for y in range(2004, 2012):
    try:
        d = enaho.load(y, "01", download_if_missing=False,
                       columns=["p1142", "factor07"])
    except Exception:
        continue
    v = pd.to_numeric(d["p1142"], errors="coerce")
    w = d["factor07"]
    denom = w[v.notna()].sum()
    share = 100 * w[v == 1].sum() / denom if denom else float("nan")
    n2 = int((v == 2).sum())
    print(f"{y:<6}{share:>13.1f}%{n2:>13}   {dic.value_labels('p1142', y, '01')}")
print()
print("A mislabel does not bend the data, only its description. A smooth ramp "
      "through 2006/2007 means code 1 IS ownership in every year.")
