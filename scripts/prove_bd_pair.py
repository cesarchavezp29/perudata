"""The b/d pair: is exactly ONE of the two columns the answer, always?

p5563b and p5563d carry the SAME label set (1 Diario ... 8 Anual). The evidence
says they are COMPLEMENTARY, not filter-and-follow-up:
    p5563d == 0  ->  p5563b holds the frequency (4=mensual: 2,997 rows)
    p5563d 1-8   ->  p5563b == 0
i.e. exactly one of the pair carries the answer and the other sits at 0. Code 0 is
"the answer is in the other column" -- not marked here.

That is rule 5's multiple-response flag in a two-column form, and MUTUAL EXCLUSIVITY
is the proof. Test it hard, on every year and every b/d pair in the module:
  * how often are BOTH non-zero? (must be ~never)
  * how often are BOTH zero?     (that is the genuine 'no answer' case)
  * how often is exactly one set? (must be the overwhelming rule)
If exclusivity holds, code 0 in either column means 'not this one'.
"""
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from perudata import enaho  # noqa: E402

for y in (2004, 2015, 2020, 2025):
    try:
        d = enaho.load(y, "05", download_if_missing=False)
    except Exception:
        continue
    pairs = []
    for c in d.columns:
        m = re.fullmatch(r"(p55\d{2,3})d", c)
        if m and f"{m.group(1)}b" in d.columns:
            pairs.append((f"{m.group(1)}b", c))
    if not pairs:
        continue
    print(f"--- {y}: {len(pairs)} b/d pairs")
    tot_excl = tot_both = tot_neither = tot_rows = 0
    for b, dd in pairs:
        vb = pd.to_numeric(d[b], errors="coerce").fillna(-1)
        vd = pd.to_numeric(d[dd], errors="coerce").fillna(-1)
        both = int(((vb > 0) & (vd > 0)).sum())
        neither = int(((vb == 0) & (vd == 0)).sum())
        excl = int(((vb > 0) ^ (vd > 0)).sum())
        tot_both += both
        tot_neither += neither
        tot_excl += excl
        tot_rows += len(d)
    print(f"      exactly ONE set : {tot_excl:>9,}")
    print(f"      BOTH set        : {tot_both:>9,}   <- must be ~0 for exclusivity")
    print(f"      NEITHER set     : {tot_neither:>9,}   <- the real 'no answer'")
