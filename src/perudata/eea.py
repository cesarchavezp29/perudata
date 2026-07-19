"""
EEA — Encuesta Económica Anual (firm/establishment microdata, 2001-2024).

Firm-level microdata: sales, costs, assets, employment and value added by
sector, with RUC (anonymized), CIIU industry code, ubigeo and expansion factor
(FACTOR_EXP). Survey year = fiscal year + 1 (EEA 2024 covers fiscal 2023).

Served as CSV on the same INEI host, one zip per (year, sector-module). There
is no code formula, so perudata ships the full 604-dataset catalog
(year, csv_code, module_name) harvested from the INEI portal catalogue.

Quickstart
----------
    from perudata import eea

    eea.years()                  # ['2001', ..., '2024']
    eea.modules(2024)            # the sector modules of EEA 2024
    df = eea.load("2110221")     # auto-download + read one module's CSV
"""
from __future__ import annotations

from importlib import resources
from pathlib import Path

from . import _core

_CATALOG = None


def catalog():
    """Full EEA catalog (year, csv_code, module_name)."""
    global _CATALOG
    if _CATALOG is None:
        import pandas as pd
        with resources.files("perudata").joinpath("catalogs/eea_catalog.csv").open(
                "r", encoding="utf-8") as f:
            _CATALOG = pd.read_csv(f, dtype={"csv_code": str, "year": int})
    return _CATALOG.copy()


def years() -> list[int]:
    return sorted(catalog()["year"].unique().tolist())


def modules(year: int):
    """The modules available for one EEA year."""
    cat = catalog()
    return cat[cat["year"] == int(year)].reset_index(drop=True)


def search(term: str):
    cat = catalog()
    terms = term.lower().split()
    # match each term against the label OR the year (newer labels drop the year,
    # e.g. "Comercio F2" for 2023 -> searching "2023" must still find it)
    hay = (cat["module_name"].str.lower() + " " + cat["year"].astype(str))
    mask = hay.apply(lambda s: all(t in s for t in terms))
    return cat[mask]


def url(csv_code: str) -> str:
    return f"{_core.BASE}/CSV/{csv_code}.zip"


def dataset_dir(csv_code: str, out: str | Path | None = None) -> Path:
    # the package stages EEA under 'eea/'; an INEI-toolkit download lands in
    # 'eea_inei/'. Prefer whichever actually holds the code.
    base = _core.data_dir(out)
    for sub in ("eea", "eea_inei"):
        cand = base / sub / str(csv_code)
        if cand.exists():
            return cand
    return base / "eea" / str(csv_code)


def download(csv_codes: list | str, out: str | Path | None = None,
             force: bool = False) -> list[Path]:
    """Download EEA module(s) by csv_code (see catalog()/modules()). Idempotent."""
    if isinstance(csv_codes, (str, int)):
        csv_codes = [csv_codes]
    root = _core.data_dir(out) / "eea"
    done: list[Path] = []
    for cc in [str(c) for c in csv_codes]:
        dest = dataset_dir(cc, out)
        if dest.exists() and list(dest.rglob("*.csv")) and not force:
            main = max(dest.rglob("*.csv"), key=lambda p: p.stat().st_size)
            print(f"[have] {cc} -> {main.name}")
            done.append(main)
            continue
        u = url(cc)
        print(f"[get ] EEA {cc}")
        try:
            zf = _core.fetch_zip(u)
        except _core.NotPublished:
            print(f"      ! NOT PUBLISHED (404): {u}")
            continue
        except _core.ServerRefused as e:
            print(f"      ! SERVER REFUSED (transient, retry later): {e}")
            continue
        members = _core.extract_members(zf, dest, (".csv", ".pdf"))
        csvs = [p for p in members if p.suffix.lower() == ".csv"]
        if not csvs:
            print("      ! no csv inside")
            _core.rmtree(dest)
            continue
        main = max(csvs, key=lambda p: p.stat().st_size)
        nr, nc = _core.csv_shape(main)
        print(f"      ok  {nr:,} rows x {nc} cols ({len(csvs)} csv)")
        _core.manifest_append(root, {
            "survey": "eea", "year": "", "module": "", "code": cc,
            "file": str(main), "n_rows": nr, "n_cols": nc,
            "bytes": main.stat().st_size,
        })
        done.append(main)
    return done


def download_year(year: int, out: str | Path | None = None,
                  force: bool = False) -> list[Path]:
    """Download every module of one EEA year."""
    return download(modules(year)["csv_code"].tolist(), out=out, force=force)


def files(csv_code: str, out: str | Path | None = None) -> list[Path]:
    d = dataset_dir(csv_code, out)
    return sorted(d.rglob("*.csv")) if d.exists() else []


def load(csv_code: str, out: str | Path | None = None,
         download_if_missing: bool = True, **read_csv_kwargs):
    """Load the main CSV of one EEA module as a DataFrame."""
    import pandas as pd
    fs = files(csv_code, out)
    if not fs:
        if not download_if_missing:
            raise FileNotFoundError(f"EEA {csv_code} not downloaded")
        download([csv_code], out=out)
        fs = files(csv_code, out)
    if not fs:
        raise RuntimeError(f"could not obtain EEA {csv_code}")
    main = max(fs, key=lambda p: p.stat().st_size)
    # EEA ships a MIX of ',' and ';' delimited files across vintages -- the 2015
    # block is ';'. Reading a ';' file as ',' does not fail: it returns ONE
    # column holding the whole line, silently. 23 of 52 modules came back like
    # that (33,350 rows x 1 col) and still looked "ok" to a row-count check.
    with open(main, "r", encoding="latin-1", errors="replace") as f:
        header = f.readline()
    sep = max([",", ";", "\t", "|"], key=header.count)
    kwargs = {"encoding": "latin-1", "low_memory": False, "sep": sep}
    kwargs.update(read_csv_kwargs)
    df = pd.read_csv(main, **kwargs)
    if df.shape[1] == 1:
        raise _core.CorruptMember(
            str(main), main.name,
            f"parsed to a single column with sep={sep!r} — the delimiter is not "
            f"one of , ; tab | . Header starts: {header[:80]!r}")
    return _core.clean_columns(df)


# ---------------------------------------------------------------------------
# EEA is chapter/Clave firm accounting -- helpers to reach a metric
# ---------------------------------------------------------------------------
def chapters(csv_code: str, out=None) -> list[str]:
    """The chapter tags present for a module ('c00','c02','c03','c09','c10',...).
    Chapter numbers VARY by formulario, so locate the one you need by CONTENT
    (the Clave it carries), not by a fixed number."""
    import re
    tags = set()
    for p in files(csv_code, out):
        m = re.search(r"_c(\w+?)_\d+", p.name.lower())
        if m:
            tags.add("c" + m.group(1))
    return sorted(tags)


def chapter(csv_code: str, chap: str, out=None, **read_csv_kwargs):
    """Load ONE chapter of an EEA module (e.g. chap='c03' Estado de Producción).

    Each EEA module ships its chapters as separate CSVs (a2023_s04_fF2_c03_1.csv);
    load() takes the largest, but a specific analysis needs a specific chapter."""
    import re
    import pandas as pd
    chap = chap.lower().lstrip("c")
    hits = [p for p in files(csv_code, out)
            if re.search(rf"_c{chap}_\d+", p.name.lower())]
    if not hits:
        raise FileNotFoundError(
            f"no chapter c{chap} in {csv_code} (have: {chapters(csv_code, out)})")
    p = max(hits, key=lambda x: x.stat().st_size)
    with open(p, "r", encoding="latin-1", errors="replace") as f:
        sep = max([",", ";", "\t", "|"], key=f.readline().count)
    df = pd.read_csv(p, encoding="latin-1", low_memory=False, sep=sep,
                     **read_csv_kwargs)
    return _core.clean_columns(df)


# the value column drifts across vintages (p01 in 2005-2019, dato1 since 2020;
# dato2/p02 hold the prior year), as does the weight (factor_exp / fac_exp, and
# absent entirely before ~2019 -- those years are a census-like enumeration and
# weight 1).
_VALUE_COLS = ("dato1", "p01", "valor", "monto")
_WEIGHT_COLS = ("factor_exp", "fac_exp", "factor", "fac")


def _value_col(df, prefer=None):
    if prefer and prefer in df.columns:
        return prefer
    for c in _VALUE_COLS:
        if c in df.columns:
            return c
    return None


def _weight_col(df):
    for c in _WEIGHT_COLS:
        if c in df.columns:
            return c
    return None


def metric(df, clave: int, value: str | None = None, weighted: bool = True) -> float:
    """Weighted total of one Clave in an EEA chapter -- the standard extraction.

    E.g. Valor Agregado = metric(chapter(code,'c03'), 88); labor compensation =
    metric(chapter(code,'c09'), 1). The reference-year value column is resolved
    across vintages (dato1 since 2020, p01 in 2005-2019; pass value= to force one,
    e.g. 'dato2'/'p02' for the prior year). The expansion weight (factor_exp /
    fac_exp) is applied when present; the pre-2019 census-style years carry no
    weight and fall back to a plain sum."""
    import pandas as pd
    col = _value_col(df, value)
    if col is None:
        raise KeyError(f"no EEA value column in {list(df.columns)}")
    row = df[pd.to_numeric(df["clave"], errors="coerce") == clave]
    v = pd.to_numeric(row[col], errors="coerce")
    wcol = _weight_col(df) if weighted else None
    if wcol is not None:
        w = pd.to_numeric(row[wcol], errors="coerce")
        # some INEI vintages ship the weight column empty (e.g. 2021 factor_exp);
        # a zero-weight total is never what is wanted -- fall back to plain sum.
        if w.fillna(0).abs().sum() > 0:
            return float((v * w).sum())
    return float(v.sum())


_CLAVES = None


def clave_concept(clave: int, sector: str | int | None = None,
                  formulario: str = "F2", year: int | None = None,
                  chapter: str | None = None) -> str | None:
    """What a Clave means, from the sector dictionaries (e.g. 88 -> 'VALOR
    AGREGADO'). Claves are reused across chapters and concepts vary by sector, so
    narrow with sector/formulario/year/chapter when a Clave is ambiguous. Note
    the dictionaries themselves list some Claves with conflicting concepts, so a
    returned name is indicative -- for VA use value_added(), not this."""
    global _CLAVES
    if _CLAVES is None:
        import pandas as pd
        from importlib import resources
        with resources.files("perudata").joinpath(
                "crosswalks/eea_clave_concept.csv").open("rb") as f:
            _CLAVES = pd.read_csv(f, encoding="utf-8", dtype=str)
    t = _CLAVES[_CLAVES["clave"] == str(clave)]
    if sector is not None:
        t = t[t["sector"] == str(sector).zfill(2)]
    if formulario is not None:
        t = t[t["formulario"].str.upper() == str(formulario).upper()]
    if year is not None:
        t = t[t["year"] == str(year)]
    if chapter is not None and "chapter" in t.columns:
        t = t[t["chapter"] == chapter]
    if t.empty:
        return None
    return t["concepto"].mode().iloc[0]


def clave_of(concept: str, sector: str | int, formulario: str = "F2",
             year: int | None = None, chapter: str | None = None,
             exact: bool = False):
    """Locate a metric: the (chapter, clave) whose concept matches, since the
    same concept sits at different Claves/chapters across sectors ('VALOR
    AGREGADO' is c03 Clave 88 in Comercio, elsewhere else). Returns a list of
    (chapter, clave) tuples.

        eea.clave_of("valor agregado", sector=4)   # -> [('c03', 88)]

    exact=True matches the concept at the START (VALOR AGREGADO, not a sub-item
    like 'valor agregado bruto de ...')."""
    global _CLAVES
    if _CLAVES is None:
        clave_concept(0)                       # populate the cache
    t = _CLAVES[_CLAVES["sector"] == str(sector).zfill(2)]
    if exact:
        t = t[t["concepto"].str.match(concept, case=False, na=False)]
    else:
        t = t[t["concepto"].str.contains(concept, case=False, na=False)]
    if formulario is not None:
        t = t[t["formulario"].str.upper() == str(formulario).upper()]
    if year is not None:
        t = t[t["year"] == str(year)]
    if chapter is not None and "chapter" in t.columns:
        t = t[t["chapter"] == chapter]
    out = []
    for r in t.itertuples(index=False):
        ch = getattr(r, "chapter", None)
        out.append((ch if isinstance(ch, str) else None, int(r.clave)))
    return sorted(set(out), key=lambda x: (x[0] or "", x[1]))


# Valor Agregado and labour compensation sit at a FIXED (chapter, Clave)
# coordinate WITHIN a questionnaire vintage -- the same across every F2 sector in
# that year -- but INEI redesigned the EEA form repeatedly, so the coordinate
# MOVES across years: VA is Clave 88 of the Estado de Producción (c03) in the
# current form but Clave 67 in the 2020-2021 form, and compensation lives in c09
# now but c10 (2020) / c08 (2021) then. We only ship coordinates VERIFIED against
# INEI's published aggregates, and return nan (never a fabricated number) for
# vintages we have not verified. The 2023-2024 coordinate reproduces INEI's
# aggregate VA (~342 mil M, ~1/3 of GDP) and 45.5% labour share to the decimal.
# (year -> (VA chapter, VA clave, compensation chapter, compensation clave))
_VA_COORDS = {
    2023: ("c03", 88, "c09", 1),
    2024: ("c03", 88, "c09", 1),
}


def _year_of(csv_code: str) -> int | None:
    t = catalog()
    hit = t[t["csv_code"] == str(csv_code)]
    return int(hit["year"].iloc[0]) if len(hit) else None


def value_added(csv_code: str, year: int | None = None, out=None) -> float:
    """Weighted total Valor Agregado (S/.) of an EEA F2 module.

    VA sits at a fixed (chapter, Clave) coordinate within a questionnaire vintage
    but the coordinate MOVES across INEI's form redesigns, so this is only
    resolved for years verified against INEI's published aggregates (currently
    2023-2024, reproducing ~342 mil M). Returns nan for unverified vintages and
    for modules with no production statement (F1 short form, Hidrocarburos). For
    an unverified year, locate VA yourself with clave_of()/metric() -- the raw
    firm-accounting layer works for all 24 years. `year` is inferred from the
    csv_code when omitted."""
    yr = year if year is not None else _year_of(csv_code)
    coord = _VA_COORDS.get(yr)
    if coord is None:
        return float("nan")
    va_ch, va_cl, _, _ = coord
    try:
        if va_ch not in chapters(csv_code, out):
            return float("nan")
        return metric(chapter(csv_code, va_ch, out), va_cl)
    except Exception:
        return float("nan")


def labor_share(csv_code: str, year: int | None = None, out=None) -> float:
    """Labour share of value added (%) for an EEA F2 module: compensation over
    VA at the vintage's verified coordinate. Reproduces INEI's aggregate 45.5%
    across all F2 sectors in 2023-2024; sectoral range ~11-69% (Servicios
    Eléctricos low, Pesca high). Returns nan for unverified vintages (see
    value_added) or when a chapter is absent."""
    yr = year if year is not None else _year_of(csv_code)
    coord = _VA_COORDS.get(yr)
    if coord is None:
        return float("nan")
    va_ch, va_cl, cp_ch, cp_cl = coord
    try:
        ch = chapters(csv_code, out)
        if va_ch not in ch or cp_ch not in ch:
            return float("nan")
        va = metric(chapter(csv_code, va_ch, out), va_cl)
        comp = metric(chapter(csv_code, cp_ch, out), cp_cl)
        return float(100 * comp / va) if va > 0 else float("nan")
    except Exception:
        return float("nan")
