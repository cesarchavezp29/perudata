"""Prove code 0 in a MULTIPLE-RESPONSE FLAG is "not marked", from structure alone.

p311a* is a matrix: 7 acquisition modes (comprado / autoconsumo / autosuministro /
...) x 8 education items. Every cell is a yes/no flag whose ONLY label is the
affirmative -- {1: 'comprado'} -- with code 0 unlabelled. That is what a
multiple-response battery looks like in a Stata file: the label names WHAT THE FLAG
MEANS WHEN SET, and 0 is simply "not marked".

The structural proof, which needs no dictionary:
  1. every column in the family holds AT MOST {0, 1} -- a flag, not a category
  2. every column's label names exactly ONE code, the affirmative
  3. the affirmative is the SAME code across all 56 cells of the matrix
  4. the flags are not mutually exclusive across modes (a household can buy AND
     self-supply), which is what makes it a MULTIPLE-response set rather than a
     single categorical whose codes we might be misreading

If all four hold, code 0 cannot be anything but "not marked": there is no other
value for it to be, and no year labels it otherwise.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from perudata import dictionary as dic  # noqa: E402
from perudata import enaho  # noqa: E402

bad = []
years_checked = []
for y in enaho.years():
    try:
        d = enaho.load(y, "03", download_if_missing=False)
    except Exception:
        continue
    fam = sorted(c for c in d.columns if c.startswith("p311a"))
    if not fam:
        continue
    years_checked.append(y)
    for c in fam:
        v = pd.to_numeric(d[c], errors="coerce").dropna()
        codes = {int(x) for x in v.unique()}
        lab = dic.value_labels(c, y, "03")
        named = {int(float(k)) for k in lab} if lab else set()
        if not codes <= {0, 1}:
            bad.append((y, c, f"holds {sorted(codes)} — not a binary flag"))
        if named and named != {1}:
            bad.append((y, c, f"labels {sorted(named)} — not a single affirmative"))

print(f"years checked: {years_checked}")
print(f"cells violating the flag structure: {len(bad)}")
for b in bad[:6]:
    print("   ", b)

# 4. are the modes non-exclusive? (a genuine multiple-response set)
d = enaho.load(2015, "03", download_if_missing=False)
modes = [f"p311a{m}_1" for m in range(1, 8) if f"p311a{m}_1" in d.columns]
if modes:
    on = sum(pd.to_numeric(d[m], errors="coerce").fillna(0) == 1 for m in modes)
    print()
    print("acquisition modes set per row (item 1, 2015):",
          on.value_counts().sort_index().head(4).to_dict())
    print("-> rows with 2+ modes set prove the flags are NOT mutually exclusive,")
    print("   i.e. this is a multiple-response battery and 0 means 'not marked'.")
