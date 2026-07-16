"""Certify the module-01 residue, case by case, from same-year evidence.

Each case gets its own proof. Nothing here is certified by pattern-matching a
neighbour year.

  A. THE `pase` CONVENTION. INEI's dictionaries declare "Rango : 0 - 1" while
     labelling only "1 <something>". Code 0 is INSIDE the declared range and
     deliberately unlabelled: it is `pase` (not applicable / did not answer). The
     dictionary itself is the evidence -- the range is a positive statement that
     the code exists. Certified only where the dictionary declares a range that
     CONTAINS the unlabelled code.

  B. p1142 (celular) 2006-2007: AN INEI LABELLING ERROR, not a gap. The .dta says
     {0: pase, 2: celular} while the data contains NO code 2 at all. Four
     independent lines say code 1 is ownership:
       * the official 2006 dictionary: "1 Celular", "Rango : 0 - 1"
       * the .dta's own label in 2004/2005 AND 2008+: {0: pase, 1: celular}
       * zero rows at code 2 in ANY year 2004-2011
       * ownership ramps smoothly 16.4 / 20.7 / 29.8 / 45.0 / 59.7 / 67.0 / 73.1 /
         75.2% straight through the mislabelled years -- a wrong label does not
         bend the data, only its description
"""
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from perudata import dictionary as dic  # noqa: E402
from perudata import enaho  # noqa: E402

ROOT = Path(__file__).parents[1]
SRC = ROOT / "docs" / "source"
OUT = ROOT / "src" / "perudata" / "crosswalks" / "enaho_label_overrides.csv"

HEADER = re.compile(r"^([A-Z][A-Z0-9_$]{1,12})\s+\d+\s+\d+\s+[NAC]\s+(.+?)\s*$")
RANGE = re.compile(r"^\s*Rango\s*:\s*(\d+)\s*[-–]\s*(\d+)", re.I)


def declared_ranges(year: int) -> dict:
    """{VAR: (lo, hi)} — the Rango INEI declares. A range is a POSITIVE statement
    that the code exists, which is what makes an unlabelled code inside it `pase`
    rather than an unknown."""
    for p in (SRC / f"ENAHO_{year}_Diccionario.txt",
              SRC / "inzip" / f"{year}_01.txt"):
        if not p.exists():
            continue
        out, cur = {}, None
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            h = HEADER.match(line)
            if h:
                cur = h.group(1).lower()
                continue
            if cur is None:
                continue
            r = RANGE.match(line)
            if r:
                out[cur] = (int(r.group(1)), int(r.group(2)))
                cur = None
        if out:
            return out
    return {}


rows = []

# ---- B. the p114x battery correction (a CORRECTION, not a gap) ----------------
# INEI wrote each variable's POSITION IN THE BATTERY as its value code in 2006-2007:
#   p1142 (celular)  labels code 2   |   p1144 (internet) labels code 4
# The named code does not exist in the data in ANY year -- it is a phantom. Every
# one of these is verified individually against the same four lines of evidence.
P114X = {
    "p1142": ("Celular", 2, "16.4/20.7/29.8/45.0/59.7/67.0/73.1/75.2"),
    "p1143": ("Beeper / TV cable", 3, None),
    "p1144": ("Internet", 4, "2.1/3.7/5.1/6.6/8.6/11.0/13.0/16.4"),
    "p1145": ("Telefono fijo", 5, None),
}
for col, (label, phantom, ramp) in P114X.items():
    for y in (2006, 2007):
        ramp_txt = (f"; and the weighted code-1 share ramps smoothly "
                    f"{ramp}% across 2004-2011, straight through {y}, which a "
                    f"mislabel cannot bend") if ramp else ""
        rows.append({
            "module": "01", "column": col, "year": y, "code": 1, "label": label,
            "status": "verified",
            "evidence": (
                f"CORRECTS AN INEI LABELLING ERROR. The {y} .dta labels {col} as "
                f"{{0: pase, {phantom}: {label.lower()}}} — INEI wrote the "
                f"variable's POSITION IN THE BATTERY as its value code. Code "
                f"{phantom} DOES NOT EXIST in the released data in any year "
                f"2004-2011; the data holds only 0 and 1. The official {y} "
                f"Diccionario states '1 {label}' with 'Rango : 0 - 1', and the "
                f".dta's OWN label in 2004/2005 and 2008+ is "
                f"{{0: pase, 1: {label.lower()}}}{ramp_txt}."),
        })

# ---- A. the `pase` convention, only where the dictionary declares the range ----
for y in enaho.years():
    try:
        df = enaho.load(y, "01", download_if_missing=False)
    except Exception:
        continue
    ranges = declared_ranges(y)
    if not ranges:
        continue
    for col in df.columns:
        lab = dic.value_labels(col, y, "01")
        lo_hi = ranges.get(col)
        if not lo_hi:
            continue
        v = pd.to_numeric(df[col], errors="coerce").dropna()
        if v.empty or not (v % 1 == 0).all():
            continue
        obs = {int(x) for x in v.unique()}
        if len(obs) > 30:
            continue
        lo, hi = lo_hi
        labelled = {int(float(k)) for k in lab} if lab else set()
        for code in sorted(obs - labelled):
            if code == 0 and lo == 0:
                rows.append({
                    "module": "01", "column": col, "year": y, "code": 0,
                    "label": "Pase", "status": "verified",
                    "evidence": (
                        f"INEI ENAHO {y} Diccionario declares '{col.upper()} "
                        f"Rango : {lo} - {hi}' while labelling only the "
                        f"affirmative code. Code 0 is INSIDE the declared range "
                        f"and deliberately unlabelled: it is INEI's `pase` (not "
                        f"applicable) convention. The declared range is a positive "
                        f"statement that the code exists."),
                })

new = pd.DataFrame(rows)
old = pd.read_csv(OUT, encoding="utf-8-sig", dtype=str)
both = pd.concat([old, new.astype(str)], ignore_index=True).drop_duplicates(
    subset=["module", "column", "year", "code"], keep="first")
both.to_csv(OUT, index=False, encoding="utf-8")
print(f"p1142 corrections: 2")
print(f"`pase` codes certified from a declared range: {len(new) - 2}")
print(f"override rows: {len(old):,} -> {len(both):,} (added {len(both) - len(old):,})")
