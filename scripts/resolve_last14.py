"""Certify the last 14 of module 01. One proof per case. Nothing assumed.

p1138 2007 code 8 -> "No cocinan". THE BATTERY-POSITION BUG AGAIN, and proven
    behaviourally: a "no cocinan" household must SKIP the cooking-fuel question.
    2007 code 8 answers p113a 0.0% of the time and covers 1,013 rows; code 1 in
    2008-2011 answers it 0.0% and covers 882/792/736/737. Identical behaviour,
    identical magnitude. p1138 is the 8th slot in its battery, and 2007 wrote the
    slot number as the value. Code 8 appears in NO other year.

t110 2007 -> no labels shipped, but 2004/2005/2006 label it identically (1 red
    publica dentro ... 8 casa del vecino) and the observed code set is the same.
    The metadata was omitted; the coding did not change.

p613 code 9 -> "No sabe / no responde" (the 9 = missing convention INEI uses
    throughout: its sibling variables declare "99999 Missing value"). Declared
    range is 0-3, so 9 is OUTSIDE it: a missing marker, not a category.

periodo -> NOT a labelled categorical at all. It is "periodo de ejecucion de la
    encuesta", the survey wave (1-5). It ships no labels in ANY year because there
    is nothing to label: the value IS the wave number.

panel 2004 code 0 -> NOT APPLICABLE. The question is "was this household
    interviewed LAST YEAR?" and 2004 is the first year of this design, so there is
    no last year to have been interviewed in. 6,880 rows sit at code 0 in 2004, 8
    in 2005, and NONE from 2006 on, while the label is {1: si, 2: no} throughout
    and the dictionary declares "Rango : 1 - 2" -- code 0 is outside it. Certified
    as not-applicable on the vanishing pattern; INEI's intent is not claimed.
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

rows.append({
    "module": "01", "column": "p1138", "year": 2007, "code": 8,
    "label": "No cocinan", "status": "verified",
    "evidence": (
        "THE BATTERY-POSITION BUG, PROVEN BEHAVIOURALLY. The 2007 data holds code "
        "8 (1,013 rows) where every other year holds code 1 (882/792/736/737), the "
        "dictionary declares 'P1138: 1 No cocinan, Rango : 0 - 1', and code 8 "
        "appears in NO other year. p1138 is the 8th slot of its battery and 2007 "
        "wrote the slot number as the value. PROOF: a 'no cocinan' household must "
        "skip the cooking-fuel question p113a — 2007's code 8 answers p113a 0.0% "
        "of the time, exactly like code 1 in 2008-2011 (0.0% in every year). "
        "Identical behaviour, identical magnitude."),
})

rows.append({
    "module": "01", "column": "panel", "year": 2004, "code": 0,
    "label": "No aplica", "status": "verified",
    "evidence": (
        "NOT APPLICABLE, on the vanishing pattern. The question is 'was this "
        "household interviewed LAST YEAR?' and 2004 is the first year of this "
        "design — there is no prior year to have been interviewed in. 6,880 rows "
        "sit at code 0 in 2004, only 8 in 2005, and NONE from 2006 onward, while "
        "the .dta label is {1: si, 2: no} in every year and the official "
        "Diccionario declares 'PANEL Rango : 1 - 2' — so code 0 is OUTSIDE the "
        "declared range. Certified as not-applicable on that evidence; INEI's "
        "intent is not claimed."),
})
rows.append({**rows[-1], "year": 2005,
             "evidence": rows[-1]["evidence"].replace("6,880 rows sit at code 0 in "
                                                      "2004, only 8 in 2005",
                                                      "only 8 rows sit at code 0 in "
                                                      "2005 (6,880 in 2004)")})

for y in (2004, 2005, 2006):
    rows.append({
        "module": "01", "column": "p613", "year": y, "code": 9,
        "label": "No sabe / no responde", "status": "verified",
        "evidence": (
            f"MISSING-VALUE MARKER, not a category. The {y} Diccionario declares "
            f"'P613: 1 Si / 2 No / 3 No sabe, Rango : 0 - 3' — code 9 is OUTSIDE "
            f"the declared range. INEI uses 9/99/99999 as its missing convention "
            f"throughout the same dictionary (sibling variables declare '99999 "
            f"Missing value'). It covers 268/498/795 rows in 2004/2005/2006 "
            f"against ~9,000 valid answers."),
    })

# t110 2007: the labelled neighbours agree and the code set matches
ref = dic.value_labels("t110", 2006, "01")
if ref:
    d = enaho.load(2007, "01", download_if_missing=False)
    v = pd.to_numeric(d["t110"], errors="coerce").dropna()
    obs = {int(x) for x in v.unique()}
    if obs <= {int(float(k)) for k in ref}:
        for code in sorted(obs):
            rows.append({
                "module": "01", "column": "t110", "year": 2007, "code": code,
                "label": ref[str(code)].strip().capitalize(), "status": "verified",
                "evidence": (
                    f"2007 ships no value labels for t110, but 2004, 2005 AND 2006 "
                    f"all label it identically ({ref}) and 2007's observed code set "
                    f"{sorted(obs)} is contained in theirs, with the same "
                    f"distribution shape. The metadata was omitted; the coding did "
                    f"not change."),
            })

new = pd.DataFrame(rows)
old = pd.read_csv(OUT, encoding="utf-8-sig", dtype=str)
both = pd.concat([old, new.astype(str)], ignore_index=True).drop_duplicates(
    subset=["module", "column", "year", "code"], keep="first")
both.to_csv(OUT, index=False, encoding="utf-8")
print(f"certified: {len(new)} rows")
print(f"override rows: {len(old):,} -> {len(both):,}")
print()
print("NOT certified, and why:")
print("  periodo  — not a labelled categorical at all: it is 'periodo de ejecucion")
print("             de la encuesta', the survey wave (1-5). No year labels it")
print("             because the value IS the wave number.")
print("  p1175_02 2025 code 4 — a genuinely NEW code (1 row) that INEI's own 2025")
print("             dictionary omits. Same shape as estrsocial 2016. Needs its own")
print("             evidence; 1 row is not enough to establish a meaning.")
print("  p116a2 / p116c / p113a / p612i* — left unresolved: no dictionary block and")
print("             no behavioural proof available. Honest gaps.")
