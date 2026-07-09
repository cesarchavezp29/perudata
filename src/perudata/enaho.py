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
            u = url(y, m)
            print(f"[get ] {y} M{m} ({MODULES[m][1]})")
            # INEI throttles bursts by answering an HTML error page with HTTP
            # 200 ("bad zip"): pace requests and cool down before retrying
            import time as _t
            zf = None
            for attempt in range(3):
                if attempt:
                    print(f"      throttled? cooldown 35s (retry {attempt}/2)")
                    _t.sleep(35)
                blob = _core.get(u)
                if blob is None:
                    continue
                zf = _core.open_zip(blob)
                if zf is not None:
                    break
            if zf is None:
                print(f"      ! download failed after retries: {u}")
                continue
            _t.sleep(2)  # pacing between files keeps the throttle asleep
            tmp = root / f"_tmp_{y}_{m}"
            members = _core.extract_members(zf, tmp, (".dta",))
            main = _core.pick_main_dta(members)
            if main is None:
                print("      ! no .dta inside the zip")
                _core.rmtree(tmp)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            main.replace(dest)
            _core.rmtree(tmp)
            ok, nr, nc = _core.verify_dta(dest)
            if not ok:
                print("      ! verification failed, removing")
                dest.unlink(missing_ok=True)
                continue
            print(f"      ok  {nr:,} rows x {nc} cols")
            _core.manifest_append(root, {
                "survey": "enaho", "year": y, "module": m, "code": YEAR_CODE[y],
                "file": str(dest), "n_rows": nr, "n_cols": nc,
                "bytes": dest.stat().st_size,
            })
            done.append(dest)
    return done


def load(year: int, module: str | int = "34", out: str | Path | None = None,
         columns: list[str] | None = None, download_if_missing: bool = True):
    """Load one (year, module) as a DataFrame, downloading it first if needed.

    Column names are lower-cased. Value labels are NOT applied (raw codes).
    """
    p = path(year, module, out)
    if not p.exists():
        if not download_if_missing:
            raise FileNotFoundError(p)
        download([year], [module], out=out)
    if not p.exists():
        raise RuntimeError(f"could not obtain ENAHO {year} module {module}")
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
