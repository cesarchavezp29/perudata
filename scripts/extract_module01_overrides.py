"""Certify module-01 labels from INEI's OFFICIAL year dictionaries.

WHY THIS IS NEEDED, and why it is one problem rather than 160: module 01 ships
almost NO value labels in the .dta for 2017-2023 (127-139 variables blank in each
of those years), while 2004-2016 and 2024-2025 mostly carry them. It is a single
systematic INEI metadata gap in a 7-year block. The published dictionaries for
those exact years DO carry the category tables, so the labels can be certified
from the authoritative source for the same year -- never carried from a neighbour.

METHOD, and every step exists because something went wrong without it:
  * parse the dictionary's own category table for the variable, in ITS year
  * CROSS-CHECK every extracted code against the codes actually observed in that
    year's microdata. An extraction that drifts by one row produces plausible,
    wrong labels (Codex hit exactly that and caught it with a regression test).
  * a code observed in the data but ABSENT from the dictionary is NOT invented:
    it is reported. INEI's own 2016 dictionary omits estrsocial code 6 while the
    data carries 12,952 of them, so the dictionary is not automatically right.
  * only rows that survive both checks are written as status=verified.
"""
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from perudata import enaho  # noqa: E402

ROOT = Path(__file__).parents[1]
SRC = ROOT / "docs" / "source"
OUT = ROOT / "src" / "perudata" / "crosswalks" / "enaho_label_overrides.csv"
MODULE = "01"

# a variable header line: NAME  len  dec  type  description
HEADER = re.compile(r"^([A-Z][A-Z0-9_$]{1,12})\s+\d+\s+\d+\s+[NAC]\s+(.+?)\s*$")
# A category line inside a variable's block. DO NOT KEY ON INDENTATION: it is an
# artifact of PDF text extraction, not of the document. pdfplumber preserves the
# leading spaces for 2015-2023 but collapses them entirely for 2005-2014, so a
# rule requiring "^\s{4,}" matched NOTHING in ten years' dictionaries -- silently,
# certifying zero while the tables sat right there in the text.
# Key on STRUCTURE instead: a header opens a block, `Rango` closes it, and inside
# a block a line that is just "<code><sep><label>" is a category. Both separators
# occur: "1 Casa independiente" (<=2019) and "1.Casa independiente" (2021+).
CATEGORY = re.compile(r"^\s*(\d{1,4})\s*[.\-]?\s*([A-Za-zÁÉÍÓÚÑáéíóúñ¿(].*?)\s*$")
RANGE = re.compile(r"^\s*Rango\s*:\s*(\d+)\s*[-–]\s*(\d+)", re.I)


def parse_dictionary(path: Path) -> tuple[dict, dict]:
    """({VARNAME: {code: label}}, {VARNAME: (lo, hi)}) from INEI's published tables.

    The declared Rango matters as much as the labels. ENAHO 2004 lists only
    "1 Electricidad" for p1121 but declares "Rango : 0 - 1" -- code 0 is INSIDE the
    declared range and deliberately UNLABELLED. That is INEI's `pase` (not
    applicable) convention, not an omission, and it is why an unlabelled code must
    never be treated as an error or invented away.
    """
    out, rng, cur = {}, {}, None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        h = HEADER.match(line)
        if h:
            cur = h.group(1).lower()
            out.setdefault(cur, {})
            continue
        if cur is None:
            continue
        r = RANGE.match(line)
        if r:
            rng[cur] = (int(r.group(1)), int(r.group(2)))
            cur = None                      # the block ends at its Rango line
            continue
        c = CATEGORY.match(line)
        if c:
            code, lab = int(c.group(1)), c.group(2).strip()
            if lab and not lab[0].isdigit():
                out[cur].setdefault(code, lab)   # first wins: later lines wrap
    return {k: v for k, v in out.items() if v}, rng


def is_enaho_dictionary(path: Path) -> bool:
    """Guard: is this document actually ENAHO's dictionary?

    The `{year}-55` URL pattern serves the EPEN (employment survey) dictionary for
    some years, not ENAHO. It downloads fine, it is a valid PDF, it is called
    Diccionario.pdf -- and it defines a DIFFERENT survey's variables. Feeding it in
    would certify labels from the wrong instrument onto ENAHO columns wherever a
    variable name happens to collide. A file being present and parseable is not
    evidence that it is the right file.
    """
    head = path.read_text(encoding="utf-8", errors="replace")[:4000].upper()
    if "EMPLEO NACIONAL" in head or "EPEN" in head:
        return False
    return "ENAHO" in head


years = []
for y in enaho.years():
    t = SRC / f"ENAHO_{y}_Diccionario.txt"
    if not t.exists():
        continue
    if not is_enaho_dictionary(t):
        print(f"[SKIP] {y}: this document is NOT ENAHO's dictionary — refusing it")
        continue
    years.append(y)
print(f"official ENAHO dictionaries available: {years}")

rows, skipped = [], []
for y in years:
    dic, ranges = parse_dictionary(SRC / f"ENAHO_{y}_Diccionario.txt")
    try:
        df = enaho.load(y, MODULE, download_if_missing=False)
    except Exception as e:  # noqa: BLE001
        print(f"[{y}] microdata not local: {e}")
        continue
    n_ok = 0
    for col in df.columns:
        table = dic.get(col)
        if not table:
            continue
        v = pd.to_numeric(df[col], errors="coerce").dropna()
        if v.empty or not (v % 1 == 0).all():
            continue
        obs = {int(x) for x in v.unique()}
        if len(obs) > 30:
            continue                        # a code list, not a categorical
        # CROSS-CHECK: every observed code must exist in the dictionary table.
        missing = obs - set(table)
        if missing:
            lo, hi = ranges.get(col, (None, None))
            in_range = lo is not None and all(lo <= c <= hi for c in missing)
            skipped.append({
                "year": y, "column": col, "codes": str(sorted(missing)),
                "declared_range": f"{lo}-{hi}" if lo is not None else "none",
                "why": ("INSIDE the declared range but deliberately unlabelled — "
                        "INEI's `pase` (not applicable) convention, NOT an omission"
                        if in_range else
                        "OUTSIDE the declared range: the dictionary and the released "
                        "data genuinely disagree — reported, never invented")})
            continue
        for code in sorted(obs):
            rows.append({"module": MODULE, "column": col, "year": y, "code": code,
                         "label": table[code], "status": "verified",
                         "evidence": f"INEI ENAHO {y} Diccionario de Datos, exact "
                                     f"category table for {col.upper()}; every "
                                     f"observed code cross-checked against the "
                                     f"{y} microdata"})
        n_ok += 1
    print(f"[{y}] {n_ok} variables certified from the official dictionary")

new = pd.DataFrame(rows)
if OUT.exists():
    old = pd.read_csv(OUT, encoding="utf-8-sig", dtype=str)
    both = pd.concat([old, new.astype(str)], ignore_index=True)
    both = both.drop_duplicates(subset=["module", "column", "year", "code"],
                               keep="first")
else:
    both = new.astype(str)
both.to_csv(OUT, index=False, encoding="utf-8")
print()
print(f"override rows total: {len(both):,} (module 01 added: {len(new):,})")
if skipped:
    s = pd.DataFrame(skipped)
    s.to_csv(Path(__file__).parent / "module01_dictionary_gaps.csv", index=False)
    print(f"REPORTED, not invented: {len(s)} variable-years where the data holds a "
          f"code the dictionary omits")
    print(s.head(8).to_string(index=False))
