"""Is the 2006/2007 mislabel the WHOLE p114x battery, or only p1142?

p1142 (celular) is proven: the .dta says {0: pase, 2: celular} in 2006/2007 while
no code 2 exists in any year, and ownership ramps smoothly through. p1143 / p1144 /
p1145 show the identical fingerprint -- code 1 unlabelled in exactly those two
years -- and they are the same question battery ("Su hogar tiene: ...").

That is a HYPOTHESIS, not a certification. Test each one the same way:
  * does the .dta label point at a code that does not exist in the data?
  * do 2004/2005 and 2008+ label code 1 as the affirmative?
  * does the official dictionary say "1 <thing>" with "Rango : 0 - 1"?
  * does the code-1 share move smoothly through 2006/2007?
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from perudata import dictionary as dic  # noqa: E402
from perudata import enaho  # noqa: E402

for col in ("p1142", "p1143", "p1144", "p1145"):
    print("=" * 74)
    print(f"{col}")
    ghost = True
    for y in range(2004, 2012):
        try:
            d = enaho.load(y, "01", download_if_missing=False,
                           columns=[col, "factor07"])
        except Exception:
            continue
        v = pd.to_numeric(d[col], errors="coerce")
        w = d["factor07"]
        denom = w[v.notna()].sum()
        share = 100 * w[v == 1].sum() / denom if denom else float("nan")
        lab = dic.value_labels(col, y, "01")
        # does the label name a code the data does not contain?
        obs = {int(x) for x in v.dropna().unique()}
        named = {int(float(k)) for k in lab} if lab else set()
        phantom = sorted(named - obs)
        print(f"   {y}  code1 {share:5.1f}%   observed {sorted(obs)}   "
              f"label {lab}   phantom codes in label: {phantom or '-'}")
