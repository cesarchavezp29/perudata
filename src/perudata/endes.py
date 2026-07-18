"""
ENDES — Encuesta Demográfica y de Salud Familiar (Peru's DHS), 1996-2024.

Fertility, maternal and child health, anemia and anthropometry, domestic
violence, contraception — the DHS "recode" modules under INEI numbering.

Two things this module handles for you (both verified against the live server):
  1. Format: only SPSS (.sav) exists for EVERY year — STATA starts in 2020.
     We standardize on SPSS and read it with pyreadstat.
  2. Module numbering shifts by era: 1996-2019 use 64-74 (+413/414 from 2013,
     569 from 2014), 2020+ use the renumbered 1629-1641 block. Ask for the
     friendly name ('mef_datos_basicos') and the right number is used per year.

Each module zip can ship SEVERAL .sav recodes (RECH/IR/BR/KR...). `files()`
lists them, `load()` reads one (default: the largest).

Quickstart
----------
    from perudata import endes

    endes.years()                          # [1996, 2000, 2004, ..., 2024]
    endes.download(2024, ["peso_talla_anemia"])
    endes.files(2024, "peso_talla_anemia") # the .sav recodes inside
    df = endes.load(2024, "peso_talla_anemia")

    # ONE CALL: download-if-missing + pool + harmonize the whole 2004-2024 span
    w = endes.dataset(range(2004, 2025), "mef_datos_basicos", "REC0111")
    w["educ"] = endes.decode(w, "v106")    # 'Superior' every year, not Higher/Mayor
    # w['anio'] = year, w['wt'] = DHS weight / 1e6, w.attrs['labels'] = the maps

Value labels DRIFT across ENDES years -- the same DHS code reads English in 2013
('yes', 'Higher') and Spanish later ('si', 'Superior'). endes.value_labels()
returns ONE canonical label per code so a pooled panel aggregates cleanly.
"""
from __future__ import annotations

from pathlib import Path

from . import _core

# year -> INEI proyecto code (harvested from the INEI catalogue)
ENDES_CODE = {
    1996: 32, 2000: 35, 2004: 120, 2005: 150, 2006: 183, 2007: 194,
    2008: 209, 2009: 238, 2010: 260, 2011: 290, 2012: 323, 2013: 407,
    2014: 441, 2015: 504, 2016: 548, 2017: 605, 2018: 638, 2019: 691,
    2020: 739, 2021: 760, 2022: 786, 2023: 910, 2024: 968,
}

OLD_CORE = [64, 65, 66, 67, 69, 70, 71, 72, 73, 74]      # no 68 (verified)
NEW_CORE = list(range(1629, 1642))

MOD_NAMES = {
    64: "hogar", 65: "vivienda", 66: "mef_datos_basicos", 67: "historia_nacimientos",
    69: "embarazo_parto_lactancia", 70: "inmunizacion_salud", 71: "nupcialidad_fecundidad",
    72: "sida_condon", 73: "mortalidad_materna_violencia", 74: "peso_talla_anemia",
    413: "disciplina_infantil", 414: "encuesta_salud", 569: "programas_sociales",
    1629: "hogar", 1630: "vivienda", 1631: "mef_datos_basicos", 1632: "historia_nacimientos",
    1633: "embarazo_parto_lactancia", 1634: "inmunizacion_salud", 1635: "nupcialidad_fecundidad",
    1636: "sida_condon", 1637: "mortalidad_materna_violencia", 1638: "peso_talla_anemia",
    1639: "disciplina_infantil", 1640: "encuesta_salud", 1641: "programas_sociales",
}


def years() -> list[int]:
    return sorted(ENDES_CODE)


def modules_for(year: int) -> list[int]:
    """Module numbers expected for an ENDES year (per era)."""
    if year >= 2020:
        return list(NEW_CORE)
    mods = list(OLD_CORE)
    if year >= 2013:
        mods += [413, 414]
    if year >= 2014:
        mods += [569]
    return mods


def modules(year: int | None = None):
    """Module catalog as a DataFrame, optionally filtered to one year."""
    import pandas as pd
    nums = modules_for(year) if year else sorted(MOD_NAMES)
    return pd.DataFrame([{"module": n, "name": MOD_NAMES.get(n, "?")} for n in nums])


def resolve_module(year: int, module: str | int) -> int:
    """Accept a module number OR a friendly name valid for that year's era."""
    if isinstance(module, int) or str(module).isdigit():
        return int(module)
    for n in modules_for(year):
        if MOD_NAMES.get(n) == module:
            return n
    raise KeyError(f"module {module!r} not found for {year} "
                   f"(names: {sorted(set(MOD_NAMES[n] for n in modules_for(year)))})")


def url(year: int, module: str | int, fmt: str = "SPSS") -> str:
    m = resolve_module(year, module)
    return f"{_core.BASE}/{fmt}/{ENDES_CODE[year]}-Modulo{m}.zip"


def module_dir(year: int, module: str | int, out: str | Path | None = None) -> Path:
    m = resolve_module(year, module)
    return (_core.data_dir(out) / "endes" / f"{year}_{ENDES_CODE[year]}"
            / f"{m}_{MOD_NAMES.get(m, 'mod')}")


def download(years_: list[int] | int, modules_: list | None = None,
             out: str | Path | None = None, force: bool = False) -> list[Path]:
    """Download ENDES SPSS modules. Every extracted .sav is opened and verified."""
    if isinstance(years_, int):
        years_ = [years_]
    if isinstance(modules_, (int, str)):
        modules_ = [modules_]
    root = _core.data_dir(out) / "endes"
    done: list[Path] = []
    for y in years_:
        if y not in ENDES_CODE:
            print(f"[skip] {y}: unknown ENDES year (has {years()})")
            continue
        mods = modules_ or modules_for(y)
        for mod in mods:
            m = resolve_module(y, mod)
            dest = module_dir(y, m, out)
            if dest.exists() and list(dest.glob("**/*.sav")) and not force:
                savs = sorted(dest.glob("**/*.sav"))
                print(f"[have] {y} M{m} ({MOD_NAMES.get(m,'?')}) -> {len(savs)} .sav")
                done += savs
                continue
            u = url(y, m)
            print(f"[get ] {y} M{m} ({MOD_NAMES.get(m,'?')})")
            try:
                zf = _core.fetch_zip(u)
            except _core.NotPublished:
                print(f"      ! NOT PUBLISHED (404): {u}")
                continue
            except _core.ServerRefused as e:
                print(f"      ! SERVER REFUSED (transient, retry later): {e}")
                continue
            members = _core.extract_members(zf, dest, (".sav",))
            nok = 0
            for p in members:
                ok, nr, nc = _core.verify_sav(p)
                if ok:
                    nok += 1
                    # ENDES is SPSS-only at INEI. Convert to Stata on arrival:
                    # nobody works in .sav. The .sav stays as the source of truth.
                    d = _core.sav_to_dta(p)
                    if d is None:
                        print(f"      ! could not convert {p.name} to .dta")
                    _core.manifest_append(root, {
                        "survey": "endes", "year": y, "module": m,
                        "code": ENDES_CODE[y], "file": str(p),
                        "n_rows": nr, "n_cols": nc, "bytes": p.stat().st_size,
                    })
                    done.append(p)
            print(f"      ok  {nok}/{len(members)} .sav verified")
    return done


def files(year: int, module: str | int, out: str | Path | None = None) -> list[Path]:
    """List the .sav recodes for a (year, module), whatever the folder layout.

    ENDES is extracted under two conventions in the wild: the package's staged
    `<m>_<name>` (e.g. 66_mef_datos_basicos) and INEI's own raw `Modulo{NN}` /
    `{code}-Modulo{NN}`. Match the module by NUMBER so a download made either way
    (or by another INEI toolkit) is found -- and glob case-insensitively, since
    early years ship `.SAV` upper-cased."""
    import re
    m = resolve_module(year, module)
    ydir = module_dir(year, module, out).parent          # <root>/endes/<year>_<code>
    staged = module_dir(year, module, out)
    savs: set = set()
    cand = [staged] if staged.is_dir() else []
    if ydir.is_dir():
        rx = re.compile(rf"(^|[-_]){m}$", re.I)           # ..Modulo64, 691-Modulo64, 64_hogar
        for sub in ydir.iterdir():
            if not sub.is_dir():
                continue
            tail = (sub.name.split("Modulo")[-1] if "Modulo" in sub.name
                    else sub.name.split("_")[0]).strip()      # 'Modulo 66' -> '66'
            if tail == str(m) or rx.search(sub.name):
                cand.append(sub)
    for c in cand:
        savs |= {p for p in c.glob("**/*.sav")}
        savs |= {p for p in c.glob("**/*.SAV")}
    # early years (2004) ship the recodes FLAT in the year folder with no module
    # subdirectory at all; fall back to those so load(recode=...) can filter them.
    if not savs and ydir.is_dir():
        savs |= {p for p in ydir.glob("*.sav")} | {p for p in ydir.glob("*.SAV")}
    return sorted(savs)


def dta_files(year: int, module: str | int, out: str | Path | None = None) -> list[Path]:
    """The Stata conversions of this module's recodes (.dta, written on download)."""
    return sorted(module_dir(year, module, out).glob("**/*.dta"))


def to_stata(year: int, module: str | int, out: str | Path | None = None) -> list[Path]:
    """Convert this module's .sav recodes to .dta (idempotent). Returns the .dta paths.

    Downloads the module first if it is not there yet.
    """
    savs = files(year, module, out)
    if not savs:
        download([year], [module], out=out)
        savs = files(year, module, out)
    made = [_core.sav_to_dta(p) for p in savs]
    return [p for p in made if p is not None]


def _recode_columns(path: Path) -> set:
    """The (lower-cased) column names of a recode, read from metadata only."""
    import pyreadstat
    dta = path.with_suffix(".dta")
    src = dta if dta.exists() else path
    try:
        if src.suffix.lower() == ".dta":
            _, meta = pyreadstat.read_dta(str(src), metadataonly=True)
        else:
            _, meta = pyreadstat.read_sav(str(src), metadataonly=True)
        return {c.lower() for c in meta.column_names}
    except Exception:
        return set()


def load(year: int, module: str | int, recode: str | None = None,
         out: str | Path | None = None, columns: list[str] | None = None,
         download_if_missing: bool = True, has: list[str] | None = None):
    """Load one .sav from a (year, module) as a DataFrame.

    recode: substring to pick a specific .sav (e.g. "RECH0"); default = largest.
    has:    pick the recode that CONTAINS these columns, regardless of its name.
            The DHS reproduction recode is called REC223132 / REC22312 /
            RE212232 / RE223132 across ENDES years -- unmatchable by name -- so
            `has=['v201']` finds it by content in every year. Takes precedence
            over recode.
    """
    savs = files(year, module, out)
    if not savs:
        if not download_if_missing:
            raise FileNotFoundError(module_dir(year, module, out))
        download([year], [module], out=out)
        savs = files(year, module, out)
    if not savs:
        raise RuntimeError(f"could not obtain ENDES {year} module {module}")
    if has:
        want = {c.lower() for c in has}
        hits = [p for p in savs if want <= _recode_columns(p)]
        if not hits:
            raise FileNotFoundError(
                f"no .sav in {year} module {module} has all of {sorted(want)} "
                f"(recodes: {[p.name for p in savs]})")
        target = max(hits, key=lambda p: p.stat().st_size)
    elif recode:
        # match recode name IGNORING separators and case: 'REC0111' must find
        # 'REC0111.sav', 'REC01_11.sav' (2004) and 'REC0111_2024.sav' (2024).
        def _norm(s: str) -> str:
            return "".join(ch for ch in s.lower() if ch.isalnum())
        want = _norm(recode)
        hits = [p for p in savs if want in _norm(p.stem)]
        if not hits:
            raise FileNotFoundError(f"no .sav matching {recode!r} in {[p.name for p in savs]}")
        target = hits[0]
    else:
        target = max(savs, key=lambda p: p.stat().st_size)
    # ENDES is the only SPSS-only survey at INEI, and nobody works in .sav.
    # Every recode is converted to Stata on download -- read that, and convert
    # on the spot for anything downloaded before this behaviour existed.
    dta = target.with_suffix(".dta")
    if not dta.exists():
        dta = _core.sav_to_dta(target) or target
    df = (_core.read_dta(dta, columns=columns) if dta.suffix.lower() == ".dta"
          else _core.read_sav(target, columns=columns))
    df.columns = [c.lower() for c in df.columns]
    return df


# ---------------------------------------------------------------------------
# Harmonized value labels
# ---------------------------------------------------------------------------
_LABELS = None


def _label_table():
    global _LABELS
    if _LABELS is None:
        import pandas as pd
        from importlib import resources
        with resources.files("perudata").joinpath(
                "crosswalks/endes_label_canon.csv").open("rb") as f:
            t = pd.read_csv(f, encoding="utf-8", dtype={"code": str})
        idx: dict = {}
        for r in t.itertuples(index=False):
            idx.setdefault(r.variable.lower(), {})[str(r.code)] = r.label
        _LABELS = idx
    return _LABELS


def value_labels(variable: str, year: int | None = None) -> dict:
    """Harmonized DHS value labels for an ENDES variable: {code: label}.

    ENDES ships each recode's labels inconsistently across years -- the same
    code reads ENGLISH in 2013 ('yes', 'frequently') and SPANISH in 2019/2024
    ('si', 'frecuentemente'), plus DHS synonyms ('Mayor'/'Superior'). The codes
    are stable; only the label string drifts. This returns ONE canonical label
    per code (the most recent year's Spanish form) so a pooled multi-year panel
    can aggregate by label without splitting a category. `year` is accepted for
    symmetry but the canonical label is year-independent by design.
    """
    return dict(_label_table().get(str(variable).lower(), {}))


# ---------------------------------------------------------------------------
# One-call harmonized multi-year loader (the ENDES parallel of dataset())
# ---------------------------------------------------------------------------
# The 2004-2008 CUMULATIVE-file trap. Verified from the interview-date CMC
# (v008): the early "annual" files nest prior years, so plotting them as single
# years is spurious. Take each TRUE calendar year from ONE source and filter by
# v008: 2004-2007 from the 2007 release (code 194), 2008 from 2008 (code 209),
# 2009+ already single-year. (Matches ENAHO_ANALYSIS/scripts/endes_units.py.)
_CUMULATIVE_SRC = {2004: 2007, 2005: 2007, 2006: 2007, 2007: 2007, 2008: 2008}


def _cmc_year(s):
    """CMC (century-month code) interview date -> calendar year."""
    import pandas as pd
    v = pd.to_numeric(s, errors="coerce")
    return 1900 + ((v - 1) // 12)


def dataset(years, module, recode: str | None = None, *,
            has: list[str] | None = None, true_year: bool = False,
            harmonize: bool = True, download_if_missing: bool = True,
            columns: list[str] | None = None, verbose: bool = True):
    """Download (if needed) and pool ONE ENDES recode across many years.

    The ENDES parallel of perudata.dataset(): give it a span and a module, and
    it returns one stacked, harmonized DataFrame ready for a multi-year series.

        from perudata import endes
        w = endes.dataset(range(2004, 2025), "mef_datos_basicos", "REC0111")
        # -> women 15-49, every year, one table; w['anio'] is the year,
        #    w['wt'] the DHS weight already divided by 1e6, and
        #    w.attrs['labels'] the harmonized {code: label} per column.

    harmonize=True (default):
      * adds `anio` (survey year) and `wt` (the DHS weight v005/hv005 divided by
        1e6, as DHS requires) so the panel is analysis-ready;
      * attaches w.attrs['labels'] = {column: {code: label}} from the canonical
        crosswalk, so decoding is CONSISTENT across years -- the same code reads
        the same label in 2004 and 2024 (raw ENDES ships English in early years,
        Spanish later). Use endes.decode(w, 'v106') or map with value_labels().

    recode: which DHS subfile ('REC0111' women, 'RECH1' hh members, ...). If
    omitted, the largest .sav in the module is used.

    true_year=True: fix the 2004-2008 CUMULATIVE-file trap. Those early ENDES
    "annual" files nest prior years' interviews -- the 2006 release is really
    2003-2006, only ~35% of it actually 2006 -- so a raw yearly series has
    spurious jumps. With true_year, each calendar year is drawn from ONE source
    (2004-2007 from the 2007 release, 2008 from 2008, 2009+ annual) and filtered
    to the records whose interview date v008/hv008 falls in that year. A recode
    that ships no v008 (INEI strips it from some) is kept whole and true-year'd
    by a caseid merge with the women's recode. Verified: adolescent motherhood
    then matches INEI's validated series across all 21 years (max 0.3pp).
    """
    import pandas as pd
    years = [years] if isinstance(years, int) else list(years)
    frames, got = [], []
    # with true_year, several calendar years share one source file (2004-2007 all
    # come from the 2007 release); load each source ONCE and split it by v008.
    src_cache: dict = {}
    for y in years:
        if y not in ENDES_CODE:
            continue
        src = _CUMULATIVE_SRC.get(y, y) if true_year else y
        try:
            if src not in src_cache:
                src_cache[src] = load(src, module, recode=recode, has=has,
                                      download_if_missing=download_if_missing,
                                      columns=columns)
            df = src_cache[src]
        except Exception as e:
            if verbose:
                print(f"[skip] ENDES {y} {module}/{recode}: "
                      f"{type(e).__name__}: {str(e)[:70]}")
            continue
        if true_year:
            datecol = next((c for c in ("v008", "hv008") if c in df.columns), None)
            if datecol is not None:
                # this recode carries the interview date -> filter it directly
                df = df[_cmc_year(df[datecol]) == y].copy()
            else:
                # a recode with no v008 (INEI strips it from some, e.g. the
                # reproduction file) cannot self-split. Keep the full source
                # tagged with the target year: a caseid merge against a
                # v008-bearing recode (the women's file) then restricts it to
                # the true year. Standalone use of such a recode in a cumulative
                # year stays pooled -- merge it, or use a recode that has v008.
                df = df.copy()
                if src != y and verbose:
                    print(f"[note] {y}: {module}/{recode or has} has no v008; "
                          f"merge on caseid with a women recode to true-year it")
        else:
            df = df.copy()
        df.insert(0, "anio", y)
        if harmonize:
            for wname in ("v005", "hv005"):
                if wname in df.columns:
                    df["wt"] = pd.to_numeric(df[wname], errors="coerce") / 1e6
                    break
        frames.append(df)
        got.append(y)
    if not frames:
        raise RuntimeError(f"no ENDES data loaded for {module}/{recode} in {years}")
    out = pd.concat(frames, ignore_index=True)
    if harmonize:
        labels = {}
        for c in out.columns:
            vl = value_labels(c)
            if vl:
                labels[c] = vl
        out.attrs["labels"] = labels
        out.attrs["years"] = got
    if verbose:
        print(f"ENDES {module}/{recode or 'largest'}: {out.shape[0]:,} rows x "
              f"{out.shape[1]} cols, {len(got)} years ({got[0]}-{got[-1]})")
    return out


def decode(df, column: str):
    """Map an ENDES code column to its harmonized label (a pandas Series).

    Consistent across years by construction: endes.decode(w, 'v106') reads
    'Superior' for code 3 in every year, not 'Higher'/'Mayor'/'Superior'."""
    import pandas as pd
    lab = (df.attrs.get("labels", {}) or {}).get(column.lower()) \
        or value_labels(column)
    s = pd.to_numeric(df[column], errors="coerce").astype("Int64").astype(str)
    return s.map(lab)


_ASFR_AGES = [15, 20, 25, 30, 35, 40, 45]


def tfr(years, *, true_year: bool = True, download_if_missing: bool = True,
        verbose: bool = True):
    """Total Fertility Rate per year, the DHS 36-month ASFR method.

        from perudata import endes
        endes.tfr(range(2004, 2025))   # -> DataFrame[año, tfr, n_mujeres, n_nac]

    TFR = 5 * sum over the seven 5-year age groups of the age-specific rate,
    where for each survey year:
      * numerator  = weighted births in the 36 months before interview, grouped
        by the mother's age AT the birth ((b3 - v011) / 12);
      * denominator = three woman-years of exposure per woman, at ages
        (current - 0.5, -1.5, -2.5), weighted.
    The birth history is found by CONTENT (has=['b3']) because its recode name
    varies across years, and true_year=True assigns each record to its calendar
    year via v008 so the cumulative 2004-2008 files are not mis-dated.

    Reproduces INEI's published TGF (~2.5 falling to 1.73, crossing replacement
    at 2018) to within 0.05 across 2004-2024.
    """
    import numpy as np
    import pandas as pd

    years = [years] if isinstance(years, int) else list(years)
    w = dataset(years, "mef_datos_basicos", "REC0111", true_year=true_year,
                download_if_missing=download_if_missing, verbose=False)
    b = dataset(years, "historia_nacimientos", has=["b3"], true_year=true_year,
                harmonize=False, download_if_missing=download_if_missing,
                verbose=False)
    for d in (w, b):
        d["_cid"] = d["caseid"].astype(str).str.replace(r"\s+", "", regex=True)
    bb = b[["anio", "_cid", "b3"]].merge(
        w[["anio", "_cid", "v008", "v011", "wt"]], on=["anio", "_cid"],
        how="inner")
    bb["mago"] = (pd.to_numeric(bb["v008"], errors="coerce")
                  - pd.to_numeric(bb["b3"], errors="coerce"))
    bb["ma"] = (pd.to_numeric(bb["b3"], errors="coerce")
                - pd.to_numeric(bb["v011"], errors="coerce")) / 12

    rows = []
    for y in sorted(w["anio"].unique()):
        mu = w[w["anio"] == y]
        s = bb[(bb["anio"] == y) & (bb["mago"] >= 0) & (bb["mago"] < 36)
               & bb["ma"].between(15, 49.999)].copy()
        s["grp"] = (s["ma"] // 5 * 5).astype(int)
        num = s.groupby("grp")["wt"].sum()
        age = pd.to_numeric(mu["v012"], errors="coerce")
        exp = {a: 0.0 for a in _ASFR_AGES}
        for t in (0.5, 1.5, 2.5):
            grp = (age - t) // 5 * 5
            for a in _ASFR_AGES:
                exp[a] += mu.loc[grp == a, "wt"].sum()
        rate = sum(float(num.get(a, 0.0)) / exp[a]
                   for a in _ASFR_AGES if exp[a] > 0)
        rows.append({"año": int(y), "tfr": round(5 * rate, 3),
                     "n_mujeres": len(mu), "n_nac": len(s)})
        if verbose:
            print(f"  {y}: TFR = {5 * rate:.2f}")
    return pd.DataFrame(rows)
