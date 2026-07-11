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
            print(f"[get ] {y} M{m} ({MOD_NAMES.get(m,'?')})")
            blob = _core.get(url(y, m))
            if blob is None:
                print("      ! 404 / download failed")
                continue
            zf = _core.open_zip(blob)
            if zf is None:
                print("      ! bad zip")
                continue
            members = _core.extract_members(zf, dest, (".sav",))
            nok = 0
            for p in members:
                ok, nr, nc = _core.verify_sav(p)
                if ok:
                    nok += 1
                    _core.manifest_append(root, {
                        "survey": "endes", "year": y, "module": m,
                        "code": ENDES_CODE[y], "file": str(p),
                        "n_rows": nr, "n_cols": nc, "bytes": p.stat().st_size,
                    })
                    done.append(p)
            print(f"      ok  {nok}/{len(members)} .sav verified")
    return done


def files(year: int, module: str | int, out: str | Path | None = None) -> list[Path]:
    """List the .sav recodes downloaded for a (year, module)."""
    return sorted(module_dir(year, module, out).glob("**/*.sav"))


def load(year: int, module: str | int, recode: str | None = None,
         out: str | Path | None = None, columns: list[str] | None = None,
         download_if_missing: bool = True):
    """Load one .sav from a (year, module) as a DataFrame.

    recode: substring to pick a specific .sav (e.g. "RECH0"); default = largest.
    """
    savs = files(year, module, out)
    if not savs:
        if not download_if_missing:
            raise FileNotFoundError(module_dir(year, module, out))
        download([year], [module], out=out)
        savs = files(year, module, out)
    if not savs:
        raise RuntimeError(f"could not obtain ENDES {year} module {module}")
    if recode:
        hits = [p for p in savs if recode.lower() in p.name.lower()]
        if not hits:
            raise FileNotFoundError(f"no .sav matching {recode!r} in {[p.name for p in savs]}")
        target = hits[0]
    else:
        target = max(savs, key=lambda p: p.stat().st_size)
    df = _core.read_sav(target, columns=columns)
    df.columns = [c.lower() for c in df.columns]
    return df
