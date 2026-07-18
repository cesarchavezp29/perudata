"""Build the ENDES value-label crosswalk: one canonical label per (variable, code).

ENDES ships DHS recode files whose value labels DRIFT across years -- 342 of 395
labelled variables in the women's recode alone carry the same code with a
different label string across years, overwhelmingly ENGLISH in 2013 vs SPANISH
in 2019/2024 ('yes'/'si', 'frequently'/'frecuentemente', 'dk'/'no sabe'), plus
DHS synonyms ('Mayor'/'Superior' for higher education). The CODES are stable
(v106==3 is higher education in every year -- the education series reproduces
9.95->10.89->11.09 yr by code), but a researcher pooling years and grouping by
LABEL splits the same category. This is the same defect harmonized away for
ENAHO, and ENDES had no crosswalk at all.

CANONICAL RULE: the label from the MOST RECENT year that documents a code. The
latest release carries INEI's current Spanish labels, and DHS codes are
standardized, so the newest label applies to every year. Harvested across all
recodes of every loadable year; a code seen only in an older year keeps that
year's label (best available). Output: crosswalks/endes_label_canon.csv with
columns variable, code, label, source_year -- and every earlier-year label that
DIFFERS is recorded in endes_label_drift.csv as the evidence of what was fixed.
"""
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import pandas as pd  # noqa: E402
import pyreadstat  # noqa: E402

from perudata import endes  # noqa: E402

OUT = Path(__file__).parents[1] / "src" / "perudata" / "crosswalks"


def codekey(c) -> str:
    try:
        f = float(c)
        return str(int(f)) if f.is_integer() else str(f)
    except (ValueError, TypeError):
        return str(c)


def nz(x: str) -> str:
    x = unicodedata.normalize("NFKD", str(x))
    return "".join(c for c in x if not unicodedata.combining(c)).lower().strip()


def harvest(year: int) -> dict:
    """{variable: {code: label}} across every recode of a year."""
    out: dict = {}
    for mod in endes.modules_for(year):
        try:
            fs = endes.files(year, mod)
        except Exception:
            continue
        for p in fs:
            if p.suffix.lower() != ".sav":
                continue
            try:
                _, meta = pyreadstat.read_sav(str(p), metadataonly=True)
            except Exception:
                continue
            for var, vals in meta.variable_value_labels.items():
                d = out.setdefault(var.lower(), {})
                for c, lab in vals.items():
                    d.setdefault(codekey(c), lab)
    return out


def main() -> int:
    years = [y for y in endes.years()
             if any(endes.files(y, m) for m in endes.modules_for(y)
                    if _safe(endes.files, y, m))]
    years = sorted(years)
    print(f"loadable ENDES years on disk: {years}")
    per_year = {y: harvest(y) for y in years}

    canon_rows, drift_rows = [], []
    all_vars = sorted(set().union(*[set(d) for d in per_year.values()]))
    for var in all_vars:
        codes = set()
        for y in years:
            codes |= set(per_year[y].get(var, {}))
        for code in codes:
            # canonical = most recent year that labels this code
            chosen = chosen_year = None
            for y in sorted(years, reverse=True):
                lab = per_year[y].get(var, {}).get(code)
                if lab:
                    chosen, chosen_year = lab, y
                    break
            if chosen is None:
                continue
            canon_rows.append({"variable": var, "code": code,
                               "label": chosen, "source_year": chosen_year})
            for y in years:
                lab = per_year[y].get(var, {}).get(code)
                if lab and nz(lab) != nz(chosen):
                    drift_rows.append({"variable": var, "code": code, "year": y,
                                       "was": lab, "canonical": chosen})

    canon = pd.DataFrame(canon_rows).sort_values(["variable", "code"])
    canon.to_csv(OUT / "endes_label_canon.csv", index=False, encoding="utf-8")
    drift = pd.DataFrame(drift_rows)
    drift.to_csv(OUT / "endes_label_drift.csv", index=False, encoding="utf-8")

    print(f"canonical (variable, code) labels: {len(canon):,} "
          f"over {canon.variable.nunique():,} variables")
    print(f"cross-year drift entries fixed:    {len(drift):,} "
          f"over {drift.variable.nunique():,} variables")
    if len(drift):
        eng = drift[drift.was.str.contains(
            r"\b(yes|no|frequently|dk|don't|both|other)\b", case=False,
            regex=True, na=False)]
        print(f"  of which English->Spanish: ~{len(eng):,}")
    return 0


def _safe(fn, *a):
    try:
        return bool(fn(*a))
    except Exception:
        return False


if __name__ == "__main__":
    sys.exit(main())
