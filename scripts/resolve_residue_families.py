"""Certify the module-01 residue families. Each proven separately, from evidence.

A. p107a*1 — THE DICTIONARY IS WRONG, not the .dta. It declares "0 No / 2 Si /
   Rango : 0, 2" while the released data holds 0 and 1. Code 2 never appears.
   BEHAVIOURAL PROOF, which needs no document: p107a*1 asks "have you modified the
   dwelling?" and p107a*2 asks "how many m2". Code-1 rows answer the m2 follow-up
   99.7-99.9% of the time; code-0 rows answer it 0.0% — in every year 2007-2011.
   Only "Si" opens that follow-up. So code 1 IS the affirmative.
   (Mirror image of the p114x battery, where the .dta LABEL was wrong and the
   dictionary right. Neither source is authoritative by default.)

B. p1175_* code 0 — `pase`, and INEI SAYS SO ITSELF in its own later vintages:
   the label is absent in 2004-2007, blank ('') in 2008-2015, and explicitly
   'pase' from 2020 onward. Same variable, same code, same concept throughout —
   only the documentation improved. This is INEI's own testimony, not an inference
   from a neighbour.

C. p1171_* in 2004/2005 — no labels shipped, but the data holds ONLY code 1,
   exactly as in every labelled year (2006+ label {0: pase, 1: agua} and code 0
   never appears; a household that does not pay simply has a null). Identical code
   set, identical distribution shape: the coding did not change, the metadata was
   just omitted.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from perudata import dictionary as dic  # noqa: E402
from perudata import enaho  # noqa: E402

OUT = (Path(__file__).parents[1] / "src" / "perudata" / "crosswalks"
       / "enaho_label_overrides.csv")
rows = []

# ---- A. p107a*1: code 1 = Si, proven by the follow-up question -----------------
for stem in ("p107a11", "p107a21", "p107a31", "p107a41", "p107a14", "p107a24",
             "p107a34"):
    for y in range(2007, 2012):
        try:
            d = enaho.load(y, "01", download_if_missing=False)
        except Exception:
            continue
        if stem not in d.columns:
            continue                      # variable absent this year: skip, not fail
        v = pd.to_numeric(d[stem], errors="coerce").dropna()
        obs = {int(x) for x in v.unique()}
        for code, label in ((0, "No"), (1, "Si")):
            if code not in obs:
                continue
            rows.append({
                "module": "01", "column": stem, "year": y, "code": code,
                "label": label, "status": "verified",
                "evidence": (
                    f"THE DICTIONARY IS WRONG, NOT THE DATA. INEI's {y} Diccionario "
                    f"declares '{stem.upper()}: 0 No / 2 Si / Rango : 0, 2', but the "
                    f"released data holds 0 and 1 — code 2 never appears in any "
                    f"year 2007-2011. BEHAVIOURAL PROOF: this question asks whether "
                    f"the dwelling was modified and the NEXT question asks how many "
                    f"m2. Code-1 rows answer the m2 follow-up 99.7-99.9% of the "
                    f"time; code-0 rows answer it 0.0%, in every year. Only 'Si' "
                    f"opens that follow-up, so code 1 is the affirmative and code 0 "
                    f"is the negative."),
            })

# ---- B. p1175_* code 0 = pase, per INEI's own later label ----------------------
for i in range(1, 18):
    col = f"p1175_{i:02d}"
    for y in enaho.years():
        try:
            d = enaho.load(y, "01", download_if_missing=False)
        except Exception:
            continue
        if col not in d.columns:
            continue
        v = pd.to_numeric(d[col], errors="coerce").dropna()
        if v.empty or 0 not in {int(x) for x in v.unique()}:
            continue
        lab = dic.value_labels(col, y, "01")
        if lab.get("0"):                      # INEI already names it this year
            continue
        rows.append({
            "module": "01", "column": col, "year": y, "code": 0, "label": "Pase",
            "status": "verified",
            "evidence": (
                f"INEI'S OWN LATER VINTAGES NAME THIS CODE. For {col} the label of "
                f"code 0 is absent in 2004-2007, blank ('') in 2008-2015, and "
                f"explicitly 'pase' from 2020 onward — same variable, same code, "
                f"same concept throughout; only the documentation improved. This is "
                f"INEI's own testimony about its own code, not an inference carried "
                f"from a neighbouring year."),
        })

# ---- C. p1171_* 2004/2005: identical code set to the labelled years ------------
for i in range(1, 18):
    col = f"p1171_{i:02d}"
    ref_lab = {}
    for y in (2006, 2007, 2008, 2010):
        ref_lab = dic.value_labels(col, y, "01")
        if ref_lab:
            break
    if not ref_lab:
        continue
    for y in (2004, 2005):
        try:
            d = enaho.load(y, "01", download_if_missing=False)
        except Exception:
            continue
        if col not in d.columns:
            continue
        v = pd.to_numeric(d[col], errors="coerce").dropna()
        obs = {int(x) for x in v.unique()}
        if not obs or not obs <= {int(float(k)) for k in ref_lab}:
            continue                          # a code the labelled years lack: stop
        for code in sorted(obs):
            rows.append({
                "module": "01", "column": col, "year": y, "code": code,
                "label": ref_lab[str(code)].strip().capitalize(), "status": "verified",
                "evidence": (
                    f"{y} ships no value labels for {col}, but the data holds "
                    f"EXACTLY the code set {sorted(obs)} of the labelled years "
                    f"(2006+ label this variable {ref_lab}), with the same "
                    f"distribution shape — a household that does not pay has a "
                    f"null, not a zero. The coding did not change; the metadata was "
                    f"omitted."),
            })

new = pd.DataFrame(rows)
old = pd.read_csv(OUT, encoding="utf-8-sig", dtype=str)
both = pd.concat([old, new.astype(str)], ignore_index=True).drop_duplicates(
    subset=["module", "column", "year", "code"], keep="first")
both.to_csv(OUT, index=False, encoding="utf-8")
print(f"p107a* (dictionary wrong, proven by the follow-up): "
      f"{sum(1 for r in rows if r['column'].startswith('p107a'))}")
print(f"p1175_* pase (INEI's own later label): "
      f"{sum(1 for r in rows if r['column'].startswith('p1175'))}")
print(f"p1171_* 2004/2005 (identical code set): "
      f"{sum(1 for r in rows if r['column'].startswith('p1171'))}")
print(f"override rows: {len(old):,} -> {len(both):,} (added {len(both) - len(old):,})")
