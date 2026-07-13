"""The standardizer: apply a per-module crosswalk so the same concept has the
same name, coding and unit in every vintage.

Contract (decided deliberately, and narrow on purpose):
  * ADDITIVE. Canonical columns are ADDED; every raw column stays. Nothing is
    hidden, and every harmonized value is auditable back to its source.
  * NOMINAL. Money is renamed and recoded, never rescaled. No deflation happens
    unless you ask for it separately. The standardizer must never silently move
    a magnitude.
  * STABLE SCHEMA. A canonical variable genuinely absent in a vintage comes back
    as an all-NA column and is MARKED in the coverage report — never silently
    missing, so pooling years can't break on a column that isn't there.
  * KEYS ARE ALWAYS NORMALIZED. Strip + zero-fill on every id column, every
    time. Idempotent on clean vintages. This is not vintage-gated: a raw merge
    of ENAHO 2004 matches 2.08% of households and reports no error at all.

Derived variables are NAMED PYTHON FUNCTIONS, not eval'd strings. The crosswalk's
`recode` column documents the formula for a human; the code below is what runs.
"""
from __future__ import annotations

import re
import unicodedata
from importlib import resources
from pathlib import Path

# id columns that must be normalized before any join, in any ENAHO module
KEY_COLS = ("conglome", "vivienda", "hogar", "codperso")


def _squash(name: str) -> str:
    """Lower-case, strip accents, drop every non-ASCII-alphanumeric character, so
    the same concept spelled differently collapses to one token.

    NOTE: a plain isalnum() filter is NOT enough — 'ñ'.isalnum() is True in
    Python, so 'año' would survive as 'año' and never match 'ano'. Decompose to
    NFKD and keep ASCII only.
    """
    import unicodedata
    s = unicodedata.normalize("NFKD", str(name).lower())
    return "".join(ch for ch in s if ch.isascii() and ch.isalnum())


# EVERY ENAHO module-year has a year column. It is just spelled a different way
# almost every time, INCLUDING as corrupted bytes:
#   'año' (341 module-years) | 'a_o' (62) | a mangled 'a?o' variant (5)
#   'aÑo' in 2025 module 85, whose real bytes are b'a\xc3\x83\xe2\x80\x98o' --
#         'año' double-encoded, i.e. MOJIBAKE, which squashes to 'aao'
# An exact token list is always one vintage behind a new encoding accident, so
# match by SHAPE (a...o) and then CHECK THE VALUES look like years.
# NOTE: `periodo` is NOT the year (it is 'periodo de ejecucion de la encuesta',
# values 1-5) and `mes` is the month.
YEAR_RE = re.compile(r"^(a[a-z]{0,3}o|anio|year)$")


def find_year_col(df, expect: int | None = None) -> str | None:
    """The year column, whatever INEI spelled or mis-encoded it this vintage.

    Matched by shape, then VALIDATED on its values: a column only counts if it
    actually holds plausible years (1996-2100), so a coincidental name match
    cannot quietly become the year.
    """
    import pandas as pd
    cands = [c for c in df.columns if YEAR_RE.match(_squash(c))]
    if not cands:
        return None
    if len(df) == 0:                    # metadata-only frame: nothing to validate
        return cands[0]
    for c in cands:
        v = pd.to_numeric(df[c], errors="coerce").dropna()
        if v.empty:
            continue
        if v.between(1996, 2100).mean() > 0.99:
            if expect is None or int(v.mode().iloc[0]) == int(expect):
                return c
    return None

_CACHE: dict[tuple[str, str], object] = {}


def crosswalk(survey: str, module: str | int):
    """The crosswalk table for one (survey, module), or raise if not written yet."""
    import pandas as pd
    key = (survey, str(module).zfill(2) if str(module).isdigit()
           and len(str(module)) <= 2 else str(module))
    if key in _CACHE:
        return _CACHE[key].copy()
    name = f"{key[0]}_{key[1]}.csv"
    path = resources.files("perudata").joinpath(f"crosswalks/{name}")
    if not path.is_file():
        raise FileNotFoundError(
            f"no crosswalk for {survey} module {key[1]} yet (have: "
            f"{', '.join(available()) or 'none'}). load(harmonize=False) still "
            f"returns the raw file, so nothing is blocked.")
    with path.open("r", encoding="utf-8") as f:
        cw = pd.read_csv(f)
    _CACHE[key] = cw
    return cw.copy()


def available() -> list[str]:
    """Which (survey, module) crosswalks exist."""
    d = resources.files("perudata").joinpath("crosswalks")
    return sorted(Path(str(p)).stem for p in d.iterdir()
                  if str(p).endswith(".csv"))


def normalize_keys(df, cols=KEY_COLS):
    """Canonicalize id columns to their NUMERIC identity. ALWAYS ON, idempotent.

    ENAHO 2004-2006 store the household id space-padded in the roster ('   5')
    and zero-padded in sumaria ('0005'). Merging the raw columns matches 2.08%
    of households in 2004 and raises nothing at all.

    Zero-FILLING to each column's own max width is NOT enough: the width is a
    property of the data present, so a module whose widest id is 4 chars and one
    whose widest is 2 still fail to meet ('0005' vs '05'). Stripping whitespace
    AND leading zeros is width-independent, so the two sides always agree.
    Leading zeros carry no meaning in these ids -- they are numeric.
    """
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            continue
        s = (out[c].astype(str).str.strip()
             .str.replace(r"\.0$", "", regex=True))
        numeric = s.str.fullmatch(r"\d+")
        # only strip zeros where the id really is all digits; leave anything
        # else exactly as it is rather than mangling an id we do not understand
        s = s.mask(numeric.fillna(False),
                   s.str.lstrip("0").replace("", "0"))
        out[c] = s
    return out


# --------------------------------------------------------------------------- #
# derived variables — the formula in the crosswalk's `recode` column, in code
# --------------------------------------------------------------------------- #
def _d_enaho34(d, canonical):
    import numpy as np
    if canonical == "area":            # CONFIRMED: reproduces INEI urban/rural
        return np.where(d["estrato"].astype("float") <= 5, 1, 2)
    if canonical == "weight_person":   # the official INEI person weight
        return d["factor07"] * d["mieperho"]
    if canonical == "poor":
        return d["pobreza"].isin([1, 2])
    if canonical == "extreme_poor":
        return d["pobreza"] == 1
    if canonical == "spending_pc_month":
        return d["gashog2d"] / (12 * d["mieperho"])
    if canonical == "income_pc_month":
        return d["inghog2d"] / (12 * d["mieperho"])
    return None


def _d_enaho02(d, canonical):
    if canonical == "hh_member":            # CONFIRMED: p204==1, all 21 vintages
        return d["p204"] == 1
    if canonical == "weight_person_welfare":
        return d["facpob07"].where(d["p204"] == 1)
    return None


def _d_enaho03(d, canonical):
    if canonical == "literate":
        # p302 is CONDITIONAL: INEI skips it when schooling already implies
        # literacy, so 75k of 108k rows are null. Only an explicit "no" is
        # illiterate; the skipped are literate. Dividing by respondents gives
        # 40% instead of the official 4.8%.
        return d["p302"] != 2
    if canonical == "illiterate":
        return d["p302"] == 2
    if canonical == "enrolled":
        return d["p306"] == 1
    if canonical == "attending":
        return d["p307"] == 1
    return None


INSURANCE = [f"p419{i}" for i in range(1, 9)]


def _d_enaho04(d, canonical):
    # p4191-p4198 are coded 0/1 in 2004 and 1/2 from 2014 -- the NAME never
    # changed. "== 1" is right in every year; "== 2" or "!= 1" is silently wrong
    # for 2004-2013.
    one = {
        "has_insurance_essalud": "p4191", "has_insurance_private": "p4192",
        "has_insurance_eps": "p4193", "has_insurance_ffaa": "p4194",
        "has_insurance_sis": "p4195", "has_insurance_university": "p4196",
        "has_insurance_school": "p4197", "has_insurance_other": "p4198",
    }
    if canonical in one:
        return d[one[canonical]] == 1
    if canonical == "has_insurance_any":
        cols = [c for c in INSURANCE if c in d.columns]
        return (d[cols] == 1).any(axis=1)
    if canonical == "disability_any":
        cols = [f"p401h{i}" for i in range(1, 7) if f"p401h{i}" in d.columns]
        return (d[cols] == 1).any(axis=1) if cols else None
    return None


def _d_enaho05(d, canonical):
    if canonical == "employed":
        return d["ocu500"] == 1
    return None


DERIVERS = {
    ("enaho", "34"): _d_enaho34,
    ("enaho", "02"): _d_enaho02,
    ("enaho", "03"): _d_enaho03,
    ("enaho", "04"): _d_enaho04,
    ("enaho", "05"): _d_enaho05,
}


def _needed_raw(row) -> list[str]:
    raw = str(row.get("raw", "") or "")
    return [r.strip() for r in raw.split(";") if r.strip()]


def apply(df, survey: str, module: str | int, year: int | None = None):
    """Harmonize one loaded module. Returns (df_with_canonical_cols, coverage).

    coverage: one row per canonical variable — did it resolve, from which raw
    name, and if not, why. That report is how you see how far standardization
    actually reaches, per year.
    """
    import pandas as pd

    mod = str(module).zfill(2) if str(module).isdigit() and len(str(module)) <= 2 \
        else str(module)
    cw = crosswalk(survey, mod)
    deriver = DERIVERS.get((survey, mod))

    out = normalize_keys(df)          # ALWAYS, before anything else
    cov = []

    for _, row in cw.iterrows():
        canon, kind = row["canonical"], row["kind"]
        if year is not None:
            ys, ye = row.get("year_start"), row.get("year_end")
            if pd.notna(ys) and year < int(ys):
                cov.append({"canonical": canon, "resolved": False, "raw": "",
                            "reason": f"not published before {int(ys)}"})
                out[canon] = pd.NA
                continue
            if pd.notna(ye) and year > int(ye):
                cov.append({"canonical": canon, "resolved": False, "raw": "",
                            "reason": f"not published after {int(ye)}"})
                out[canon] = pd.NA
                continue

        need = _needed_raw(row)
        missing = [r for r in need if r not in out.columns]

        # `year` is spelled FOUR ways across ENAHO ('año', 'a_o', a mangled byte
        # variant, and 'aÑo'). EVERY module-year has one -- resolve it by shape,
        # never by a hard-coded name.
        if canon == "year":
            col = find_year_col(out)
            if col is not None:
                out[canon] = pd.to_numeric(out[col], errors="coerce")
                cov.append({"canonical": canon, "resolved": True, "raw": col,
                            "reason": ""})
                continue
            if year is not None:      # last resort: we always know what we asked for
                out[canon] = int(year)
                cov.append({"canonical": canon, "resolved": True, "raw": "",
                            "reason": "no year column found — filled from the "
                                      "requested year"})
                continue

        if missing:
            # STABLE SCHEMA: absent -> all-NA column, and SAY SO. Never silent.
            out[canon] = pd.NA
            cov.append({"canonical": canon, "resolved": False,
                        "raw": ";".join(need),
                        "reason": f"raw column(s) absent: {', '.join(missing)}"})
            continue

        if kind == "rename":
            out[canon] = out[need[0]]
        else:                                   # derive / recode
            val = deriver(out, canon) if deriver else None
            if val is None:
                out[canon] = pd.NA
                cov.append({"canonical": canon, "resolved": False,
                            "raw": ";".join(need),
                            "reason": "no deriver implemented"})
                continue
            out[canon] = val
        cov.append({"canonical": canon, "resolved": True, "raw": ";".join(need),
                    "reason": ""})

    coverage = pd.DataFrame(cov)
    # attrs must hold only plain data: pandas COMPARES attrs when merging frames,
    # and a DataFrame in there raises "Can only compare identically-labeled...".
    out.attrs["coverage"] = cov                       # list of dicts, not a frame
    out.attrs["harmonized"] = f"{survey}/{mod}"
    return out, coverage
