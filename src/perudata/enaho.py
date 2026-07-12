"""
ENAHO — Encuesta Nacional de Hogares (annual cross-section, 2004-2025).

Peru's flagship household survey: income, spending, poverty, employment,
education, health, social programs and governance. INEI publishes the official
poverty numbers FROM this survey, and perudata reproduces them to 0.0pp
(see perudata.validate).

Quickstart
----------
    from perudata import enaho

    enaho.years()                    # [2004, ..., 2025]
    enaho.modules()                  # DataFrame: module number, name, description
    enaho.download([2024], ["34"])   # sumaria (poverty/income) for 2024
    df = enaho.load(2024, "34")      # auto-downloads if missing -> DataFrame

Files land in ./peru_raw (override with out= or the PERUDATA_DIR env var):
    peru_raw/enaho/sumaria/enaho-2024-34.dta
"""
from __future__ import annotations

from pathlib import Path

from . import _core

# year -> INEI proyecto code. CONTENT-VERIFIED: each code confirmed by reading
# the internal `año` variable inside its Modulo34 file. Codes are NOT
# chronological (279 is 2010, while 280-285 are 2004-2009).
YEAR_CODE = {
    2004: 280, 2005: 281, 2006: 282, 2007: 283, 2008: 284, 2009: 285,
    2010: 279, 2011: 291, 2012: 324, 2013: 404, 2014: 440, 2015: 498,
    2016: 546, 2017: 603, 2018: 634, 2019: 687, 2020: 737, 2021: 759,
    2022: 784, 2023: 906, 2024: 966, 2025: 1031,
}

# module number -> (folder name, description). Descriptions verified against
# each .dta's internal dataset label.
MODULES = {
    "01": ("vivienda_hogar",         "Caracteristicas de la Vivienda y el Hogar"),
    "02": ("miembros",               "Caracteristicas de los Miembros del Hogar"),
    "03": ("educacion",              "Educacion"),
    "04": ("salud",                  "Salud"),
    "05": ("empleo_ingreso",         "Empleo e Ingreso"),
    "07": ("gastos_alimentos",       "Gastos en Alimentos y Bebidas comprados (p601)"),
    "08": ("gastos_alim_no_comprado","Alimentos/bebidas sin compra: autoconsumo, donacion (p602)"),
    "09": ("gastos_mant_vivienda",   "Mantenimiento de la Vivienda (p603)"),
    "10": ("gastos_transp_comunic",  "Transportes y Comunicaciones (p604)"),
    "11": ("gastos_serv_vivienda",   "Servicios a la Vivienda (p605)"),
    "12": ("gastos_esparcimiento",   "Esparcimiento, Diversion y Cultura (p606)"),
    "13": ("gastos_vestido_calzado", "Vestido y Calzado (p607)"),
    "15": ("gastos_transferencias",  "Gastos de Transferencias (p609)"),
    "16": ("gastos_muebles_enseres", "Muebles y Enseres (p610)"),
    "17": ("gastos_otros_byss",      "Otros Bienes y Servicios (p611)"),
    "18": ("equipamiento_hogar",     "Equipamiento del Hogar (p612)"),
    "22": ("prod_agricola",          "Produccion Agricola (persona x cultivo)"),
    "23": ("subprod_agricola",       "Subproductos Agricolas"),
    "24": ("prod_forestal",          "Produccion Forestal"),
    "25": ("gastos_agropecuarios",   "Gastos en Actividades Agropecuarias y Forestales"),
    "26": ("prod_pecuaria",          "Produccion Pecuaria (persona x especie)"),
    "27": ("subprod_pecuario",       "Subproductos Pecuarios"),
    "28": ("trabajadores_agro",      "Trabajadores y Equipo Agropecuario"),
    "34": ("sumaria",                "Sumaria - Variables Calculadas (ingreso/gasto/pobreza)"),
    "37": ("programas_sociales",     "Programas Sociales"),
    "77": ("agro_actividad_persona", "Productor Agropecuario: actividad por persona"),
    "78": ("gastos_cuidados_pers",   "Bienes y Servicios de Cuidados Personales"),
    "84": ("participacion_ciudadana","Participacion Ciudadana (Capitulo 800)"),
    "85": ("gobernabilidad",         "Gobernabilidad, Democracia y Transparencia"),
}

DEFAULT_MODULES = ["01", "02", "03", "04", "05", "34", "85"]


def years() -> list[int]:
    """Survey years with a verified download code."""
    return sorted(YEAR_CODE)


def latest_year() -> int:
    return max(YEAR_CODE)


def modules():
    """Module catalog as a DataFrame (module, name, description)."""
    import pandas as pd
    return pd.DataFrame(
        [{"module": m, "name": v[0], "description": v[1]} for m, v in MODULES.items()]
    )


def url(year: int, module: str | int) -> str:
    """Direct INEI download URL for a (year, module) STATA zip."""
    module = str(module).zfill(2)
    return f"{_core.BASE}/STATA/{YEAR_CODE[year]}-Modulo{module}.zip"


def path(year: int, module: str | int, out: str | Path | None = None) -> Path:
    """Local path where load()/download() put this (year, module)."""
    module = str(module).zfill(2)
    folder = MODULES[module][0]
    return _core.data_dir(out) / "enaho" / folder / f"enaho-{year}-{module}.dta"


def download(years_: list[int] | int, modules_: list | None = None,
             out: str | Path | None = None, force: bool = False) -> list[Path]:
    """Download ENAHO STATA modules. Re-runnable: existing verified files are skipped.

    Parameters
    ----------
    years_   : one year or a list of years (2004-2025)
    modules_ : module numbers, default the 7 core modules
               ["01","02","03","04","05","34","85"]
    out      : data root (default ./peru_raw or PERUDATA_DIR)
    force    : re-download even if the file exists

    Returns the list of local .dta paths that exist after the run.
    """
    if isinstance(years_, int):
        years_ = [years_]
    if isinstance(modules_, (int, str)):
        modules_ = [modules_]
    modules_ = [str(m).zfill(2) for m in (modules_ or DEFAULT_MODULES)]
    root = _core.data_dir(out) / "enaho"
    done: list[Path] = []

    for y in years_:
        if y not in YEAR_CODE:
            print(f"[skip] {y}: unknown year (try enaho.discover({y}))")
            continue
        for m in modules_:
            if m not in MODULES:
                print(f"[skip] module {m}: unknown")
                continue
            dest = path(y, m, out)
            if dest.exists() and not force:
                print(f"[have] {y} M{m} -> {dest}")
                done.append(dest)
                continue
            try:
                dest = _download_one(y, m, out=out)
            except _core.NotPublished as e:
                # the catalog claims this module but INEI has no such file. That
                # disagreement is a CATALOG fact, not a bug to retry.
                print(f"      ! NOT PUBLISHED (404): {e.url}")
                continue
            except _core.ServerRefused as e:
                print(f"      ! SERVER REFUSED (transient, retry later): {e}")
                continue
            except _core.CorruptMember as e:
                print(f"      ! CORRUPT DATA MEMBER (upstream, not transient): {e}")
                continue
            done.append(dest)
    return done


def _download_one(year: int, module: str, out: str | Path | None = None) -> Path:
    """Fetch exactly one (year, module) or raise a TYPED failure.

    NotPublished  — INEI 404s the URL: the file does not exist. Do not retry.
    ServerRefused — throttle/timeout: transient, retry later.
    CorruptMember — the archive is fine but its .dta is damaged upstream.
    """
    root = _core.data_dir(out) / "enaho"
    dest = path(year, module, out)
    u = url(year, module)
    zf = _core.fetch_zip(u)                      # raises NotPublished/ServerRefused
    tmp = root / f"_tmp_{year}_{module}"
    members = _core.extract_members(zf, tmp, (".dta",))
    main = _core.pick_main_dta(members)
    if main is None:
        listed = [n for n in zf.namelist() if n.lower().endswith(".dta")]
        _core.rmtree(tmp)
        if listed:
            raise _core.CorruptMember(u, listed[0], "member would not extract")
        raise _core.CorruptMember(u, "<none>", "archive contains no .dta at all")
    dest.parent.mkdir(parents=True, exist_ok=True)
    main.replace(dest)
    _core.rmtree(tmp)
    ok, nr, nc = _core.verify_dta(dest)
    if not ok:
        dest.unlink(missing_ok=True)
        raise _core.CorruptMember(u, main.name, "extracted .dta would not open")
    print(f"      ok  {nr:,} rows x {nc} cols")
    _core.manifest_append(root, {
        "survey": "enaho", "year": year, "module": module,
        "code": YEAR_CODE[year], "file": str(dest), "n_rows": nr, "n_cols": nc,
        "bytes": dest.stat().st_size,
    })
    return dest


def load(year: int, module: str | int = "34", out: str | Path | None = None,
         columns: list[str] | None = None, download_if_missing: bool = True,
         harmonize: bool = False):
    """Load one (year, module) as a DataFrame, downloading it first if needed.

    Column names are lower-cased. Value labels are NOT applied (raw codes).

    harmonize=True ADDS canonical columns from the module's crosswalk (same name,
    coding and unit in every vintage) alongside the raw ones — nothing is dropped
    and money stays NOMINAL. Ids are normalized. The per-variable coverage report
    lands in df.attrs["coverage"]. Modules without a crosswalk raise, and
    harmonize=False always returns the raw file.
    """
    p = path(year, module, out)
    if not p.exists():
        if not download_if_missing:
            raise FileNotFoundError(p)
        # let the TYPED failure reach the caller: "not published" and "server
        # refused" demand opposite responses, and collapsing both into one
        # RuntimeError is what made ENAHO 2015 look like a throttle for three
        # rounds when the real cause was a corrupt member in our own gate.
        module_ = str(module).zfill(2)
        print(f"[get ] {year} M{module_} ({MODULES[module_][1]})")
        _download_one(year, module_, out=out)
    df = _core.read_dta(p, columns=columns)
    df.columns = [c.lower() for c in df.columns]
    if harmonize:
        from . import harmonize as _h
        df, _ = _h.apply(df, "enaho", module, year=year)
    return df


# --------------------------------------------------------------------------- #
# combine
# --------------------------------------------------------------------------- #
HH_KEY = ["conglome", "vivienda", "hogar"]
PERSON_KEY = HH_KEY + ["codperso"]

# granularity per module, verified empirically (one row per what?).
# ITEM modules must be AGGREGATED before they can be joined -- combine() refuses
# them rather than silently exploding the row count.
HOUSEHOLD_MODULES = {"01", "34", "37", "84", "85"}
PERSON_MODULES = {"02", "03", "04", "05", "25", "28"}


def combine(year: int, modules: list[str] | None = None,
            level: str = "person", out: str | Path | None = None):
    """Join several ENAHO modules into ONE analysis table, safely.

    This exists because doing it by hand is demonstrably dangerous:

      * KEYS. ENAHO 2004-2006 pad the household id differently in different
        modules ('   5' vs '0005'). A raw merge matches 2.08% of households in
        2004 and RAISES NOTHING. Keys are normalized here, always.
      * POPULATION. The module-02 roster counts everyone in the dwelling
        (37.13M weighted in 2025). INEI's welfare population counts HABITUAL
        RESIDENTS only (p204==1 -> 34.86M). Picking the wrong one moves the
        population by 2.3 million people. combine() attaches BOTH, named apart.
      * WEIGHTS. The right weight CHANGES BY MODULE: 03 carries factor07 (and
        factora07), 04 carries factor07, 05 carries only fac500a. A naive merge
        inherits whichever came along for the ride.

    level="person"    -> one row per person (household vars broadcast onto people)
    level="household" -> one row per household (household modules only)

    Returns a DataFrame; df.attrs["combine"] records what was joined and how many
    rows matched at each step.
    """
    import pandas as pd
    from . import harmonize as _h

    modules = [str(m).zfill(2) for m in (modules or ["34", "02"])]
    bad = [m for m in modules
           if m not in HOUSEHOLD_MODULES and m not in PERSON_MODULES]
    if bad:
        raise ValueError(
            f"module(s) {bad} are ITEM-level (many rows per household: a product, "
            f"an expense). Joining them here would multiply your rows. Aggregate "
            f"them to household/person first, then merge.")
    if level == "household" and any(m in PERSON_MODULES for m in modules):
        raise ValueError(
            f"level='household' but {[m for m in modules if m in PERSON_MODULES]} "
            f"is person-level. Use level='person', or drop the person module.")

    meta: dict = {"year": year, "level": level, "modules": modules, "steps": []}

    def _load(m):
        df = load(year, m, out=out)
        return _h.normalize_keys(df)          # ALWAYS, before any join

    hh_mods = [m for m in modules if m in HOUSEHOLD_MODULES]
    pe_mods = [m for m in modules if m in PERSON_MODULES]

    # ---- household spine ---------------------------------------------------
    base = None
    for m in hh_mods:
        d = _load(m)
        if m == "34":                          # canonical poverty/income/weights
            d, _ = _h.apply(d, "enaho", "34", year=year)
        d = d.drop_duplicates(HH_KEY)
        base = d if base is None else base.merge(
            d, on=HH_KEY, how="inner", suffixes=("", f"_m{m}"))
        meta["steps"].append({"module": m, "level": "household", "rows": len(base)})

    if level == "household":
        if base is None:
            raise ValueError("no household module requested")
        base.attrs["combine"] = meta
        return base

    # ---- person spine ------------------------------------------------------
    person = None
    for m in pe_mods:
        d = _load(m)
        if m == "02":
            d, _ = _h.apply(d, "enaho", "02", year=year)   # hh_member + weights
        d = d.drop_duplicates(PERSON_KEY)
        person = d if person is None else person.merge(
            d, on=PERSON_KEY, how="outer", suffixes=("", f"_m{m}"))
        meta["steps"].append({"module": m, "level": "person", "rows": len(person)})

    if person is None:
        raise ValueError("level='person' needs at least one person module "
                         "(e.g. '02')")

    if base is not None:
        n_before = len(person)
        person = person.merge(base, on=HH_KEY, how="left",
                              suffixes=("", "_hh"))
        matched = person[HH_KEY].notna().all(axis=1).sum()
        meta["steps"].append({"module": "household->person broadcast",
                              "rows": len(person),
                              "matched_pct": round(100 * matched / n_before, 2)})

    person.attrs["combine"] = meta
    return person


def discover(year: int, lo: int = 967, hi: int = 1200) -> list[int]:
    """Scan the INEI server for the proyecto code of a not-yet-mapped year.

    Checks Modulo34 for each candidate code. VERIFY the internal `año`
    variable before trusting a hit (codes are not chronological).
    """
    hits = []
    for code in range(lo, hi + 1):
        if _core.head_ok(f"{_core.BASE}/STATA/{code}-Modulo34.zip"):
            print(f"  code {code} -> 200 OK")
            hits.append(code)
    return hits
