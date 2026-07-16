"""Prove each residue family before certifying. No family is assumed from another.

  p107a*1 : the dictionary declares "0 No / 2 Si / Rango : 0, 2" but the DATA holds
            0 and 1. The phantom pattern again, with the source reversed: here the
            DICTIONARY is wrong, not the .dta label. Test: is code 1 the
            affirmative? Then the p107a*2 follow-up (m2 built) must be answered by
            code-1 rows and skipped by code-0 rows.
  p1175_* : is code 0 `pase`? INEI's OWN later vintage answers it -- 2025 labels
            {0: 'pase'} and 2010 labels {0: ''}. Test the label across vintages.
  p1171_* : 2004/2005 ship no labels. 2006+ label {0: pase, 1: agua}. Test: does
            2004 hold the same code set with the same meaning?
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
print("p107a21: does code 1 behave like 'Si'? The follow-up question decides.")
print("  p107a21 = '¿Ha realizado modificacion?'  p107a22 = 'Cuantos m2'")
print("  If 1 = Si, then code-1 rows ANSWER the m2 follow-up and code-0 rows skip it.")
for y in (2007, 2008, 2009, 2010, 2011):
    try:
        d = enaho.load(y, "01", download_if_missing=False,
                       columns=["p107a21", "p107a22"])
    except Exception:
        continue
    a = pd.to_numeric(d["p107a21"], errors="coerce")
    b = pd.to_numeric(d["p107a22"], errors="coerce")
    r1 = 100 * b[a == 1].notna().mean() if (a == 1).any() else float("nan")
    r0 = 100 * b[a == 0].notna().mean() if (a == 0).any() else float("nan")
    print(f"   {y}: code1 -> m2 answered {r1:5.1f}% | code0 -> m2 answered {r0:5.1f}%"
          f" | codes {sorted(a.dropna().unique().tolist())}")

print()
print("=" * 78)
print("p1175_02: what does INEI itself call code 0, across vintages?")
for y in (2004, 2006, 2008, 2010, 2015, 2020, 2025):
    try:
        enaho.load(y, "01", download_if_missing=False, columns=["p1175_02"])
    except Exception:
        continue
    lab = dic.value_labels("p1175_02", y, "01")
    print(f"   {y}: {lab}")

print()
print("=" * 78)
print("p1171_01: 2004/2005 ship no labels. Same code set as the labelled years?")
for y in (2004, 2005, 2006, 2010):
    try:
        d = enaho.load(y, "01", download_if_missing=False, columns=["p1171_01"])
    except Exception:
        continue
    v = pd.to_numeric(d["p1171_01"], errors="coerce")
    print(f"   {y}: codes {sorted(v.dropna().unique().tolist())} | "
          f"labels {dic.value_labels('p1171_01', y, '01')} | "
          f"nulls {int(v.isna().sum()):,} of {len(v):,}")
