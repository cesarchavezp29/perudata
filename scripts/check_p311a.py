"""What is the p311a* family, and is code 0 a category or `pase`?

62 of module 03's 105 unresolved variables are p311a1_*. They all block on the same
thing: code 0 unlabelled. That is the `pase` signature, but rule 1 needs a DECLARED
RANGE to certify it, and no dictionary block was found.

So look at the data. A multiple-response battery (p311a1_0 ... p311a1_7) is a set of
yes/no flags: "which of these did you do?". If code 0 is `pase`/no and the positive
code is the answer, then:
  * each column holds exactly two values
  * the positive code should be the SAME across the family
  * a respondent's row should be answerable across the battery
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from perudata import dictionary as dic  # noqa: E402
from perudata import enaho  # noqa: E402

d = enaho.load(2015, "03", download_if_missing=False)
fam = sorted(c for c in d.columns if c.startswith("p311a"))
print(f"the p311a family in 2015: {fam}")
print()
print(f"{'column':12}{'codes':>18}{'label':>42}")
for c in fam:
    v = pd.to_numeric(d[c], errors="coerce")
    codes = sorted(v.dropna().unique().tolist())
    lab = dic.value_labels(c, 2015, "03")
    print(f"{c:12}{str(codes):>18}{str(lab)[:40]:>42}")

print()
print("does ANY year label this family?")
for y in enaho.years():
    try:
        f = enaho.load(y, "03", download_if_missing=False)
    except Exception:
        continue
    got = {c: dic.value_labels(c, y, "03") for c in fam if c in f.columns}
    named = {c: l for c, l in got.items() if l}
    if named:
        print(f"   {y}: {len(named)} of {len(got)} labelled — "
              f"e.g. {list(named.items())[0]}")

print()
print("variable label (what the question IS):")
v = dic.variable("p311a1_1")
if len(v):
    print("  ", v[["year", "label"]].drop_duplicates("label").head(2).to_string(
        index=False))
