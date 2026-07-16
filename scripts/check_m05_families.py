"""Module 05's 134: three different things, only one of which is a labelling gap.

  p556* (76) — the biggest family. What is it?
  p505/p506 — CIIU/CIUO CLASSIFICATION NAMESPACES. A 4-digit official code
              (7526 = a CIIU industry) is not a categorical anyone labels: the code
              IS the identity, per the published standard. These should never have
              entered the label pipeline at all.
  p207 = -126 in 2009 — SEX CANNOT BE -126. That is the signature of a Stata int8
              overflow (-128..127). A genuine data defect, not a metadata gap, and
              inventing a label for it would be inventing data.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from perudata import dictionary as dic  # noqa: E402
from perudata import enaho  # noqa: E402

print("=" * 78)
print("p207 (sex) = -126 in 2009: how many rows, and what does the year look like?")
d = enaho.load(2009, "05", download_if_missing=False)
v = pd.to_numeric(d["p207"], errors="coerce")
print("   value counts:", v.value_counts(dropna=False).head(5).to_dict())
print("   label:", dic.value_labels("p207", 2009, "05"))
print("   -> -128..127 is int8's range. A value at -126 in a 1/2 variable is an")
print("      overflow artifact, not a category. NEVER label it.")

print()
print("=" * 78)
print("the p556 family: what is it?")
v = dic.variable("p556")
if len(v):
    print("  ", v[["year", "label"]].drop_duplicates("label").head(2).to_string(
        index=False))
d15 = enaho.load(2015, "05", download_if_missing=False)
fam = sorted(c for c in d15.columns if c.startswith("p556"))[:10]
print("   columns:", fam)
for c in fam[:5]:
    vv = pd.to_numeric(d15[c], errors="coerce").dropna()
    print(f"   {c}: codes {sorted(vv.unique().tolist())[:6]} | "
          f"label {dic.value_labels(c, 2015, '05')}")

print()
print("=" * 78)
print("p505/p506: classification namespaces, not categoricals")
for col in ("p505", "p506", "p505r4", "p506r4"):
    if col not in d15.columns:
        continue
    vv = pd.to_numeric(d15[col], errors="coerce").dropna()
    print(f"   {col}: {vv.nunique():,} distinct codes, range "
          f"{int(vv.min())}-{int(vv.max())} | label {dic.value_labels(col, 2015, '05')}")
