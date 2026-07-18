"""
EPE / EPEN — Peru's permanent employment surveys (2001-2026).

Four series, all person-level employment microdata:
  - EPE  Lima Metropolitana y Callao (legacy, monthly/quarterly, 2001+)
  - EPEN Ciudades (national cities, quarterly + annual)
  - EPEN Departamentos (departmental, annual)
  - EPEN Lima Metropolitana y Callao (new series)

EPEN is ONLY served as CSV (STATA/SPSS 404 on the INEI host), one consolidated
CSV per dataset under Modulo76-style codes. There is no year->code formula, so
perudata ships a VERIFIED catalog of 279 datasets (code, label) discovered by
probing the server and opening every file. `search()` it, then `load()` by code.

Quickstart
----------
    from perudata import epen

    epen.catalog()                 # DataFrame: 279 verified datasets
    epen.search("dpto 2024")       # find departmental 2024
    df = epen.load(997)            # auto-download + read the CSV
"""
from __future__ import annotations

import re
from importlib import resources
from pathlib import Path

from . import _core

_CATALOG = None


def catalog():
    """The verified EPE/EPEN dataset catalog (code, module, label)."""
    global _CATALOG
    if _CATALOG is None:
        import pandas as pd
        with resources.files("perudata").joinpath("catalogs/epen_catalog.csv").open(
                "r", encoding="utf-8") as f:
            _CATALOG = pd.read_csv(f)
    return _CATALOG.copy()


def search(term: str):
    """Case/accent-insensitive substring search over the catalog labels."""
    cat = catalog()
    terms = term.lower().split()
    mask = cat["label"].str.lower().apply(lambda s: all(t in s for t in terms))
    return cat[mask]


def url(code: int, module: int = 76) -> str:
    return f"{_core.BASE}/CSV/{code}-Modulo{module}.zip"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:60]


def dataset_dir(code: int, out: str | Path | None = None) -> Path | None:
    # the package stages EPEN under 'epen/'; a download made by INEI's own
    # toolkit lands in 'epen_inei/'. Look in both so either is found.
    base = _core.data_dir(out)
    for sub in ("epen", "epen_inei"):
        hits = sorted((base / sub).glob(f"{code}_*")) \
            if (base / sub).is_dir() else []
        if hits:
            return hits[0]
    return None


def download(codes: list[int] | int, out: str | Path | None = None,
             force: bool = False) -> list[Path]:
    """Download EPE/EPEN dataset(s) by catalog code. Idempotent."""
    if isinstance(codes, int):
        codes = [codes]
    root = _core.data_dir(out) / "epen"
    cat = catalog().set_index("code")
    done: list[Path] = []
    for code in codes:
        existing = dataset_dir(code, out)
        if existing and list(existing.rglob("*.csv")) and not force:
            main = max(existing.rglob("*.csv"), key=lambda p: p.stat().st_size)
            print(f"[have] {code} -> {main.name}")
            done.append(main)
            continue
        module = int(cat.loc[code, "module"]) if code in cat.index else 76
        label = str(cat.loc[code, "label"]) if code in cat.index else str(code)
        u = url(code, module)
        print(f"[get ] {code} ({label})")
        try:
            zf = _core.fetch_zip(u)
        except _core.NotPublished:
            print(f"      ! NOT PUBLISHED (404): {u}")
            continue
        except _core.ServerRefused as e:
            print(f"      ! SERVER REFUSED (transient, retry later): {e}")
            continue
        csvs = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csvs:
            print(f"      ! no csv inside ({zf.namelist()[:3]})")
            continue
        main_name = max(csvs, key=lambda n: zf.getinfo(n).file_size)
        dest = root / f"{code}_{_slug(Path(main_name).stem)}"
        members = _core.extract_members(zf, dest, (".csv", ".pdf"))
        main = dest / main_name
        nr, nc = _core.csv_shape(main)
        if nr == 0:
            print("      ! empty csv, removing")
            _core.rmtree(dest)
            continue
        print(f"      ok  {nr:,} rows x {nc} cols")
        _core.manifest_append(root, {
            "survey": "epen", "year": "", "module": module, "code": code,
            "file": str(main), "n_rows": nr, "n_cols": nc,
            "bytes": main.stat().st_size,
        })
        done.append(main)
    return done


def load(code: int, out: str | Path | None = None,
         download_if_missing: bool = True, **read_csv_kwargs):
    """Load one EPE/EPEN dataset by code as a DataFrame (latin-1, low_memory off)."""
    import pandas as pd

    def _data(dd):
        # EPEN spans three formats by vintage: modern CSV, and the 2005-2015
        # legacy EPE Lima served as .sav (+ .dbf). Read whichever is present.
        return (list(dd.rglob("*.csv")) or list(dd.rglob("*.CSV"))
                or list(dd.rglob("*.sav")) or list(dd.rglob("*.SAV"))
                or list(dd.rglob("*.dbf")) or list(dd.rglob("*.DBF")))

    d = dataset_dir(code, out)
    if d is None or not _data(d):
        if not download_if_missing:
            raise FileNotFoundError(f"EPEN code {code} not downloaded")
        download([code], out=out)
        d = dataset_dir(code, out)
    if d is None:
        raise RuntimeError(f"could not obtain EPEN dataset {code}")
    main = max(_data(d), key=lambda p: p.stat().st_size)
    ext = main.suffix.lower()
    if ext == ".sav":
        df = _core.read_sav(main)
    elif ext == ".dbf":
        from dbfread import DBF
        df = pd.DataFrame(iter(DBF(str(main), encoding="latin-1")))
    else:
        # EPEN CSVs mix ',' and ';' delimiters -- sniff the header line
        with open(main, "r", encoding="latin-1", errors="replace") as f:
            header = f.readline()
        sep = max([",", ";", "\t", "|"], key=header.count)
        kwargs = {"encoding": "latin-1", "low_memory": False, "sep": sep}
        kwargs.update(read_csv_kwargs)
        df = pd.read_csv(main, **kwargs)
    return _core.clean_columns(df)


# ---------------------------------------------------------------------------
# Harmonized value labels (harvested from the .sav era; see build_epen_labels.py)
# ---------------------------------------------------------------------------
_LABELS = None


def _label_table():
    global _LABELS
    if _LABELS is None:
        import pandas as pd
        from importlib import resources
        with resources.files("perudata").joinpath(
                "crosswalks/epen_label_canon.csv").open("rb") as f:
            t = pd.read_csv(f, encoding="utf-8", dtype={"code": str})
        idx: dict = {}
        for r in t.itertuples(index=False):
            idx.setdefault(r.variable.lower(), {})[str(r.code)] = r.label
        _LABELS = idx
    return _LABELS


def value_labels(variable: str) -> dict:
    """Harmonized value labels for an EPEN variable: {code: label}.

    EPEN ships as CSV (codes only); the labels are harvested from the legacy
    EPE .sav era and reconciled to one canonical Spanish label per code. Covers
    the variables the .sav files carry (the p-series and shared structural vars
    like estrato/dominio). The modern CSV era renamed many questions to a
    c-series; mapping those needs the EPEN questionnaire crosswalk (pending).
    """
    return dict(_label_table().get(str(variable).lower(), {}))
