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
         columns: list[str] | None = None, download_if_missing: bool = True):
    """Load one (year, module) as a DataFrame, downloading it first if needed.

    Column names are lower-cased. Value labels are NOT applied (raw codes).
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
    return df


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
