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
    return _core.data_dir(out) / "eea" / str(csv_code)


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
