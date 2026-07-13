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


# The expansion factor is ALSO renamed across vintages, module by module. Module
# 85 (gobernabilidad) alone uses FOUR names:
#   factor07 (2004-09, 2012-13) | facgob07 (2010-11, 2014) | facgob_p (2020)
#   famiegob07 (2025) -- 'factor de expansion anual de gobernabilidad', which no
#   'fac...' substring search finds.
# So the weight is resolved by SHAPE + VALUE, never by a fixed name.
WEIGHT_RE = re.compile(r"(fac|peso|factor|expan)")


def find_weight_cols(df) -> list[str]:
    """Every column that behaves like an expansion factor: name looks like one
    AND the values are positive and large (a weight expands to a population)."""
    import pandas as pd
    out = []
    for c in df.columns:
        s = _squash(c)
        if not (WEIGHT_RE.search(s) or s.endswith("gob07")):
            continue
        v = pd.to_numeric(df[c], errors="coerce").dropna()
        if len(v) and (v > 0).mean() > 0.99 and v.median() > 5:
            out.append(c)
    return out


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
    """Which HAND-CONFIRMED (survey, module) crosswalks exist."""
    d = resources.files("perudata").joinpath("crosswalks")
    return sorted(Path(str(p)).stem for p in d.iterdir()
                  if str(p).endswith(".csv") and "_auto_" not in str(p))


def stability(module: str | int, status: str | None = None):
    """EVERY variable of a module, with whether it is safe to pool across years.

    The hand-confirmed crosswalks cover the ~135 variables that carry the
    headline statistics. This covers ALL 5,678, computed from INEI's own metadata
    in the files:

      stable       — present every year, value labels never move
      code_change  — THE CODING MOVED UNDER A STABLE NAME. 546 variables do this.
                     It is the silent-error class: the health-insurance flags go
                     from 0/1 to 1/2 in 2012 while the name and the label stay put.
      label_change — the question was REWORDED (a redefinition may be hiding)
      intermittent — not collected every year
      continuous   — a count or an amount, no codes to drift

        harmonize.stability("04", status="code_change")   # what will bite me?
    """
    import pandas as pd
    m = str(module).zfill(2)
    p = resources.files("perudata").joinpath(f"crosswalks/enaho_auto_{m}.csv")
    if not p.is_file():
        raise FileNotFoundError(f"no auto-crosswalk for module {m}")
    with p.open("r", encoding="utf-8") as f:
        df = pd.read_csv(f)
    if status:
        df = df[df["status"] == status]
    return df[["canonical", "status", "year_start", "year_end", "note"]]


def unsafe(module: str | int):
    """The variables of a module that CANNOT be pooled blindly: their coding or
    their question moved across years. Look here before trusting a raw column."""
    import pandas as pd
    df = stability(module)
    return df[df["status"].isin(["code_change", "label_change", "intermittent"])]


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
    if canonical == "weight_hh_x_size":  # official person weight, HOUSEHOLD grain
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


def _d_enaho05(d, canonical, year=None):
    import numpy as np
    import pandas as pd

    if canonical == "employed":
        return d["ocu500"] == 1

    if canonical == "informal":
        # PREFER INEI'S OWN FLAG WHERE IT EXISTS. `ocupinf` is published for
        # 2007-2023 and IS the official series; the constructed rule agrees with
        # it at 92-97% but carries a -0.8 to -1.3pp bias, so using the rule in a
        # year where INEI ships the answer needlessly drifts from official.
        # Construct ONLY where INEI gives us nothing: 2004-2006 and 2024+.
        if "ocupinf" in d.columns:
            oc = pd.to_numeric(d["ocupinf"], errors="coerce")
            if oc.notna().mean() > 0.5:
                return (oc == 1).where(
                    pd.to_numeric(d.get("ocu500"), errors="coerce") == 1)
        # INEI's OPERATIONAL RULE for empleo informal (OIT 17 CIET). INEI ships
        # its own flag `ocupinf` ONLY for 2007-2023 -- it never existed for
        # 2004-2006 and was DROPPED from 2024 (the 2024 dictionary, 493 pages,
        # does not mention 'informal' once). So a series that spans 2004-2025 has
        # to be constructed, and this is the rule, validated against ocupinf at
        # ~97% agreement and <1pp bias:
        #   * TFNR (5) and 'otro' (7)          -> ALWAYS informal
        #   * salaried: empleado(3)/obrero(4)/trabajador del hogar(6)
        #                                      -> informal if NO FORMAL CONTRACT
        #   * empleador(1)/independiente(2)    -> informal if the unit is NOT
        #                                         REGISTERED (informal sector)
        # TWO TRAPS, both of the silent kind:
        #   - p511a's coding MOVES: 'locacion de servicios' (informal) is code 6
        #     up to 2011 and code 5 from 2012, while code 6 from 2012 means
        #     'regimen especial' (FORMAL). So formal contract = {1,2} to 2011 and
        #     {1,2,6} from 2012.
        #   - the registration variable is RENAMED: p510a (2004-2011, 1=si/2=no)
        #     -> p510a1 (2012+, 1/2=registered, 3=no). Looking only for p510a1
        #     reports it "100% missing" before 2012 -- it is just the old name.
        # NOTE: social security is operationalised by CONTRACT, not by pension
        # affiliation (+7pp bias) or EsSalud (-5pp bias).
        cat = pd.to_numeric(d.get("p507"), errors="coerce").values
        y = int(year) if year else 2025
        formal_contract = [1, 2] if y <= 2011 else [1, 2, 6]
        cf = pd.to_numeric(d.get("p511a"), errors="coerce").isin(
            formal_contract).values
        if "p510a1" in d.columns:
            sector_formal = pd.to_numeric(d["p510a1"], errors="coerce").isin(
                [1, 2]).values
        elif "p510a" in d.columns:
            sector_formal = (pd.to_numeric(d["p510a"], errors="coerce") == 1).values
        else:
            return None
        inf = np.zeros(len(d), bool)
        inf[np.isin(cat, [5, 7])] = True
        dep = np.isin(cat, [3, 4, 6])
        inf[dep] = ~cf[dep]
        emp = np.isin(cat, [1, 2])
        inf[emp] = ~sector_formal[emp]
        out = pd.Series(inf, index=d.index).where(
            pd.to_numeric(d.get("ocu500"), errors="coerce") == 1)

        # CONSTRUCTIBILITY GATE. The rule needs the contract (p511a) for salaried
        # workers and the registration for the self-employed. In 2004 p511a is
        # MISSING for ~49% of them, and the rule then over-estimates badly (it
        # would print 93% against a published ~81%). Refuse rather than publish a
        # misleading number. In 2020 contract coverage collapses to 0.59 because
        # the COVID survey ran partly by telephone -- that is why the rule reads
        # +7pp above the official ocupinf that year, and it is a data limitation,
        # not a bug.
        occ = pd.to_numeric(d.get("ocu500"), errors="coerce") == 1
        sal = occ & pd.Series(dep, index=d.index)
        if sal.any():
            cov = 1 - pd.to_numeric(d.get("p511a"), errors="coerce")[sal].isna().mean()
            if cov < 0.8:
                return pd.Series(pd.NA, index=d.index, dtype="object")
        return out

    if canonical == "informal_official":
        return (pd.to_numeric(d["ocupinf"], errors="coerce") == 1
                if "ocupinf" in d.columns else None)

    if canonical == "informal_source":
        # WHICH SOURCE PRODUCED `informal` IN THIS ROW. Without this column the
        # series contains INVISIBLE METHOD BREAKS: 2006 (constructed, 83.5) ->
        # 2007 (ocupinf, 80.1) looks like a 3.5-point collapse in informality and
        # is mostly the source switching. Measured bias of the constructed rule
        # against INEI's own flag:
        #     2007-2011 (INEI's pre-2012 method):  +2.61 pp (over-estimates)
        #     2012-2023 (INEI's direct method)  :  -2.04 pp, shrinking to -0.8
        #                                          by 2023
        # So 2005-2006 constructed values run ~2.6pp HOT (84.6 / 83.5 raw ->
        # ~82 / ~81 comparable), while 2024-2025 run ~0.8-1.0pp COLD (72.5 / 71.8
        # raw -> ~73.3 / ~72.7 comparable). Never plot this series without
        # splitting or annotating by this column.
        y = int(year) if year else 2025
        if "ocupinf" in d.columns and pd.to_numeric(
                d["ocupinf"], errors="coerce").notna().mean() > 0.5:
            return pd.Series("ocupinf (INEI official)", index=d.index)
        sal = np.isin(pd.to_numeric(d.get("p507"), errors="coerce").values, [3, 4, 6])
        occ = pd.to_numeric(d.get("ocu500"), errors="coerce") == 1
        m = occ & pd.Series(sal, index=d.index)
        cov = (1 - pd.to_numeric(d.get("p511a"), errors="coerce")[m].isna().mean()
               if m.any() else 0.0)
        if cov < 0.8:
            return pd.Series("NOT CONSTRUCTIBLE", index=d.index)
        return pd.Series(
            f"constructed ({'pre-2012 rule, runs ~+2.6pp hot' if y <= 2011 else 'post-2012 rule, runs ~0.8-1.0pp cold'})",
            index=d.index)
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
            if deriver is _d_enaho05:
                val = deriver(out, canon, year=year)
            else:
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

    # EVERY raw column of the module comes back too (the contract is additive).
    # Attach the stability status of each one, so a column that changes its coding
    # or its question across years cannot be pooled unknowingly.
    try:
        st = stability(mod)
        st = st[st["canonical"].isin(out.columns)]
        risky = st[st["status"].isin(["code_change", "label_change", "intermittent"])]
        out.attrs["stability"] = st.to_dict("records")
        out.attrs["unsafe_columns"] = risky["canonical"].tolist()
    except FileNotFoundError:
        out.attrs["stability"] = []
        out.attrs["unsafe_columns"] = []
    return out, coverage
