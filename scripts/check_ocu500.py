"""ocu500 code 0: the highest-stakes unresolved code in module 05.

ocu500 is INEI's PEA indicator (1 Ocupado / 2 Desocupado abierto / 3 Desocupado
oculto / 4 No PEA), declared "Rango: 1 - 4". The data holds code 0 in 2004-2008,
OUTSIDE the declared range. Every employment statistic keys off this variable --
including the informality series that reproduces INEI's published figure -- so a
wrong reading here corrupts the module's headline numbers.

Two candidate meanings, and they are NOT interchangeable:
  * "not applicable / under the working-age floor" -- ocu500 is only defined for
    people old enough to work, so children would sit outside the PEA classification
  * something else entirely

The test: WHO carries code 0? If it is exactly the under-14s (ENAHO's module-05
universe starts at 14), the code is the below-age-floor marker and the age
distribution will say so unambiguously.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from perudata import enaho  # noqa: E402

print("ocu500: which years hold code 0, and how many rows?")
for y in (2004, 2006, 2008, 2009, 2012, 2020, 2025):
    try:
        d = enaho.load(y, "05", download_if_missing=False)
    except Exception:
        continue
    v = pd.to_numeric(d["ocu500"], errors="coerce")
    vc = v.value_counts(dropna=False).sort_index()
    print(f"   {y}: {vc.to_dict()}")

print()
print("WHO are the code-0 rows? (age is the deciding evidence)")
for y in (2004, 2006, 2008):
    try:
        d = enaho.load(y, "05", download_if_missing=False)
    except Exception:
        continue
    if "p208a" not in d.columns:
        print(f"   {y}: no age column in module 05")
        continue
    v = pd.to_numeric(d["ocu500"], errors="coerce")
    age = pd.to_numeric(d["p208a"], errors="coerce")
    z = age[v == 0]
    nz = age[v.isin([1, 2, 3, 4])]
    print(f"   {y}: code 0 -> age min {z.min()}, max {z.max()}, median {z.median()}"
          f" (n={len(z):,})")
    print(f"        codes 1-4 -> age min {nz.min()}, max {nz.max()} (n={len(nz):,})")
