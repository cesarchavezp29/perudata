"""Audit the newly-resolved consumption/production modules against ground truth.

The numeric modules (07-28, 77, 78) were resolved from INEI's published
dictionaries, which for these modules are messier than the survey modules: the
PDF->txt conversion runs a question's stem onto its value line, so a value label
can absorb text that is not part of it. INEI's OWN .dta embedded labels are
clean here, so the .dta is the ground truth and the dictionary is the suspect.

This does two things, and FIXES nothing on its own -- it writes a report:

1. CONTAMINATED LABELS. A resolved label is contaminated when the .dta gives a
   short label for that exact (column, code) and the resolved label merely
   PREFIXES it with more words -- e.g. dict '1. Si  compraron o le regalaron
   alguno...' where the .dta says 'si'. Detected as: normalized .dta label is a
   strict prefix of the normalized resolved label AND the resolved label is much
   longer. The .dta label is the truth.

2. FLAG BATTERIES LABELLED 'Pase'. The acquisition batteries (p601a1-a7 in
   module 07, p606e* in module 78, etc.) ask '¿cómo obtuvo el ...?' and code 0
   is 'No marcado', not 'Pase' -- the item WAS obtained, just not this way. The
   discriminator, proven on module 03, is exhaustiveness: load only the battery
   columns (memory-frugal even at 9M rows) and if no in-universe row marks none
   of the siblings, code 0 is 'No marcado'. Reported per battery with the count.
"""
import os
import re
import sys
import unicodedata
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")
sys.path.insert(0, "src")

import pandas as pd  # noqa: E402
import pyreadstat  # noqa: E402

from perudata import enaho  # noqa: E402

ROOT = Path(__file__).parents[1]
XW = ROOT / "src" / "perudata" / "crosswalks" / "enaho_label_overrides.csv"
NEW = ["07", "08", "09", "10", "11", "12", "13", "15", "16", "17", "18",
       "22", "23", "24", "25", "26", "27", "28", "77", "78"]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.lower()).strip()


def dta_labels(mod: str, year: int) -> dict:
    p = enaho.path(year, mod)
    if not p.exists():
        return {}
    try:
        _, meta = pyreadstat.read_dta(str(p), metadataonly=True)
    except Exception:
        return {}
    out = {}
    for col, d in meta.variable_value_labels.items():
        out[col.lower()] = {
            (str(int(c)) if float(c).is_integer() else str(c)): v
            for c, v in d.items()}
    return out


def find_contaminated(o: pd.DataFrame) -> pd.DataFrame:
    hits = []
    for mod in NEW:
        sub = o[o.module == mod]
        by_year = {y: dta_labels(mod, int(y)) for y in sub.year.unique()}
        for r in sub.itertuples(index=False):
            d = by_year.get(r.year, {}).get(r.column, {})
            if r.code not in d:
                continue
            clean, got = norm(d[r.code]), norm(r.label)
            if clean and got != clean and got.startswith(clean) \
                    and len(got) > len(clean) + 4:
                hits.append({"module": mod, "column": r.column, "year": r.year,
                             "code": r.code, "resolved": r.label,
                             "dta_clean": d[r.code]})
    return pd.DataFrame(hits)


def battery_exhaustive(mod: str, stem_re: str) -> dict:
    """For each acquisition battery, is code 0 'No marcado' (exhaustive)?"""
    verdict = {}
    for y in enaho.years():
        p = enaho.path(y, mod)
        if not p.exists():
            continue
        try:
            _, meta = pyreadstat.read_dta(str(p), metadataonly=True)
        except Exception:
            continue
        fam = sorted(c for c in meta.column_names if re.fullmatch(stem_re, c.lower()))
        if len(fam) < 2:
            continue
        try:
            df, _ = pyreadstat.read_dta(str(p), usecols=fam)
        except Exception:
            continue
        v = df.apply(pd.to_numeric, errors="coerce")
        inuni = ~v.isna().all(axis=1)
        marks = (v == 1).sum(axis=1)
        none = int((marks[inuni] == 0).sum())
        verdict.setdefault(mod, []).append(
            (y, int(inuni.sum()), none, int((marks[inuni] >= 2).sum())))
    return verdict


def main() -> int:
    o = pd.read_csv(XW, encoding="utf-8-sig", dtype=str)

    print("== 1. CONTAMINATED LABELS (dta clean label is a strict prefix) ==")
    con = find_contaminated(o)
    if con.empty:
        print("   none")
    else:
        con.to_csv(ROOT / "scripts" / "contaminated_labels.csv", index=False,
                   encoding="utf-8")
        g = con.groupby(["module", "column", "code"]).agg(
            n=("year", "size"), resolved=("resolved", "first"),
            clean=("dta_clean", "first")).reset_index()
        print(f"   {len(con)} rows, {len(g)} (col,code) groups:")
        for r in g.head(30).itertuples(index=False):
            print(f"   {r.module} {r.column:<10} c{r.code}: "
                  f"{r.resolved[:44]!r} -> {r.clean!r} ({r.n})")

    print("\n== 2. ACQUISITION BATTERIES labelled 'Pase' at code 0 ==")
    z = o[(o.code == "0") & (o.label == "Pase") & o.module.isin(NEW)]
    stems = sorted(z.column.unique())
    # group by battery stem (strip trailing digits)
    fams = sorted({(m, re.sub(r"\d+$", "", c))
                   for m, c in zip(z.module, z.column)})
    for mod, stem in fams:
        rx = re.escape(stem) + r"\d+"
        cols = [c for c in z[z.module == mod].column if re.fullmatch(rx, c)]
        if len(cols) < 2:
            continue
        v = battery_exhaustive(mod, rx)
        rec = v.get(mod, [])
        if not rec:
            continue
        exhaustive = all(none == 0 or none <= 2 for _, _, none, _ in rec)
        multi = any(m2 > 0 for *_, m2 in rec)
        tag = ("-> No marcado (exhaustive, multi-response)"
               if exhaustive and multi else "-> keep Pase (rows mark nothing)")
        tot_none = sum(none for *_, none, _ in rec)
        print(f"   {mod} {stem}* ({len(cols)} slots): markNONE total={tot_none} "
              f"{tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
