"""ocu500 code 0: test every hypothesis that the data can actually settle.

I declined this after ONE test (below-working-age), which the ages killed: code-0
rows are 14-95, median 28. That was too early. Other hypotheses are testable here:

  H1. THE SECTION WAS NEVER ADMINISTERED. If ocu500=0 means the employment
      questionnaire was not applied to this person, their module-05 answers must be
      EMPTY -- no occupation, no hours, no income. A person INEI classified into the
      PEA (1-4) answers; a person it did not classify has nothing to classify FROM.

  H2. THEY ARE ABSENT / PROXY-REFUSED. Then they would sit in the roster but carry
      no employment answers, same signature as H1 -- distinguishable by p204
      (habitual resident) or the roster's absence flags.

  H3. IT IS A SEPARATE UNIVERSE. Check whether code-0 rows are systematically
      different: age distribution, sex, education, the year's collection mode.

The discriminator is H1: measure the ANSWER RATE of module-05 variables for code-0
rows against codes 1-4. If it is ~0% versus ~100%, ocu500=0 is "not interviewed for
employment" and nothing else fits.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from perudata import enaho  # noqa: E402

# core employment questions: asked of anyone in the employment universe
PROBES = ["p501", "p502", "p505", "p506", "p507", "p513t", "ocupinf", "fac500a"]

print("H1: do ocu500=0 rows answer ANY module-05 question?")
print(f"{'year':<6}{'probe':<9}{'answered | code 0':>19}{'answered | codes 1-4':>22}")
for y in (2004, 2012, 2020, 2025):
    try:
        d = enaho.load(y, "05", download_if_missing=False)
    except Exception:
        continue
    v = pd.to_numeric(d["ocu500"], errors="coerce")
    z, nz = v == 0, v.between(1, 4)
    if not z.any():
        continue
    for probe in PROBES:
        if probe not in d.columns:
            continue
        s = pd.to_numeric(d[probe], errors="coerce")
        a0 = 100 * s[z].notna().mean()
        a1 = 100 * s[nz].notna().mean()
        print(f"{y:<6}{probe:<9}{a0:>17.1f}%{a1:>21.1f}%")
    print()

print("=" * 74)
print("H3: are the code-0 rows a different population?")
for y in (2004, 2020, 2025):
    try:
        d = enaho.load(y, "05", download_if_missing=False)
    except Exception:
        continue
    v = pd.to_numeric(d["ocu500"], errors="coerce")
    z, nz = v == 0, v.between(1, 4)
    if not z.any():
        continue
    bits = [f"n={int(z.sum()):,}"]
    for c, name in (("p208a", "age"), ("p207", "sex")):
        if c in d.columns:
            s = pd.to_numeric(d[c], errors="coerce")
            bits.append(f"{name} median {s[z].median()} vs {s[nz].median()}")
    print(f"   {y}: {' | '.join(bits)}")
