"""
ENAHO Panel — the longitudinal version of ENAHO (same households re-interviewed).

Each panel *release* is a cumulative file stacking several waves of the SAME
households — the raw material for true poverty dynamics, transitions and
fixed-effects estimation (instead of pseudo-panels from the cross-section).

Releases (release year = LAST wave covered):
    2011 -> 2007-2011 (the original 5-wave balanced panel)
    2015-2023 -> overlapping ~5-year windows

Two traps this module handles for you:
  1. Module numbering changes by era: old releases (<=2017) use zero-padded
     01/03/04/05/34 (+1314 miembros in 2016-17), new releases (>=2018) use the
     1474-1479 block.
  2. Old files are WIDE (one row per household, columns suffixed _07.._11);
     `load_long()` melts them into a tidy long panel automatically.

Weights: use per-wave `fac_NN`/`factor07_NN` to reproduce an ANNUAL number,
and `fac_panel<window>` for DYNAMICS on the balanced subsample. Mixing them
fabricates fake discrepancies.

Quickstart
----------
    from perudata import panel

    panel.releases()                    # [2011, 2015, ..., 2023]
    panel.download(2011, ["34"])        # sumaria of the 2007-2011 panel
    df, meta = panel.load_long(2011, "34")
    meta["waves"]                       # [2007, 2008, 2009, 2010, 2011]
"""
from __future__ import annotations

import re
from pathlib import Path

from . import _core

# panel release year -> INEI proyecto code (verified by reading internal año)
PANEL_CODE = {
    2011: 302, 2015: 529, 2016: 614, 2017: 612, 2018: 651,
    2019: 699, 2020: 743, 2021: 763, 2022: 845, 2023: 912,
}

OLD_MODULES = {
    "01":   ("vivienda_hogar", "Caracteristicas de la Vivienda y del Hogar"),
    "02":   ("miembros",       "Caracteristicas de los Miembros del Hogar"),
    "03":   ("educacion",      "Educacion"),
    "04":   ("salud",          "Salud"),
    "05":   ("empleo_ingreso", "Empleo e Ingresos"),
    "34":   ("sumaria",        "Sumaria - Variables Calculadas"),
    "1314": ("miembros",       "Miembros del Hogar (2016-2017)"),
}
NEW_MODULES = {
    "1474": ("vivienda_hogar", "Caracteristicas de la Vivienda y del Hogar"),
    "1475": ("educacion",      "Educacion"),
    "1476": ("salud",          "Salud"),
    "1477": ("empleo_ingreso", "Empleo e Ingresos"),
    "1478": ("sumaria",        "Sumaria - Variables Calculadas"),
    "1479": ("miembros",       "Miembros del Hogar"),
}

# friendly aliases: name -> module number per era
ALIASES = {"sumaria": ("34", "1478"), "educacion": ("03", "1475"),
           "salud": ("04", "1476"), "empleo_ingreso": ("05", "1477"),
           "vivienda_hogar": ("01", "1474"), "miembros": ("1314", "1479")}


def releases() -> list[int]:
    return sorted(PANEL_CODE)


def modules_for(release: int) -> dict:
    """Module dict (number -> (folder, description)) for a release's era."""
    return NEW_MODULES if release >= 2018 else OLD_MODULES


def resolve_module(release: int, module: str | int) -> str:
    """Accept a module number OR a friendly name ('sumaria') for any era."""
    m = str(module)
    if m in ALIASES:
        m = ALIASES[m][1] if release >= 2018 else ALIASES[m][0]
    if m not in modules_for(release):
        raise KeyError(f"module {module!r} not available for release {release} "
                       f"(has {list(modules_for(release))})")
    return m


def url(release: int, module: str | int) -> str:
    m = resolve_module(release, module)
    return f"{_core.BASE}/STATA/{PANEL_CODE[release]}-Modulo{m}.zip"


def path(release: int, module: str | int, out: str | Path | None = None) -> Path:
    m = resolve_module(release, module)
    folder = modules_for(release)[m][0]
    return (_core.data_dir(out) / "enaho_panel" / f"{release}_{PANEL_CODE[release]}"
            / f"panel-{release}-{folder}.dta")


def download(releases_: list[int] | int, modules_: list | None = None,
             out: str | Path | None = None, force: bool = False) -> list[Path]:
    """Download panel releases. Default module: sumaria (poverty dynamics)."""
    if isinstance(releases_, int):
        releases_ = [releases_]
    if isinstance(modules_, (int, str)):
        modules_ = [modules_]
    modules_ = modules_ or ["sumaria"]
    root = _core.data_dir(out) / "enaho_panel"
    done: list[Path] = []
    for rel in releases_:
        if rel not in PANEL_CODE:
            print(f"[skip] release {rel}: unknown (has {releases()})")
            continue
        for mod in modules_:
            m = resolve_module(rel, mod)
            dest = path(rel, m, out)
            if dest.exists() and not force:
                print(f"[have] panel {rel} {m} -> {dest}")
                done.append(dest)
                continue
            print(f"[get ] panel {rel} M{m} ({modules_for(rel)[m][1]})")
            blob = _core.get(url(rel, m))
            if blob is None:
                print("      ! download failed")
                continue
            zf = _core.open_zip(blob)
            if zf is None:
                print("      ! bad zip")
                continue
            tmp = root / f"_tmp_{rel}_{m}"
            members = _core.extract_members(zf, tmp, (".dta",))
            main = _core.pick_main_dta(members)
            if main is None:
                print("      ! no .dta in zip")
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
                "survey": "enaho_panel", "year": rel, "module": m,
                "code": PANEL_CODE[rel], "file": str(dest),
                "n_rows": nr, "n_cols": nc, "bytes": dest.stat().st_size,
            })
            done.append(dest)
    return done


# --------------------------------------------------------------------------- #
# tidy loader (wide -> long)
# --------------------------------------------------------------------------- #
ANCHOR_SETS = [
    ["conglome", "vivienda", "hogar"],
    ["cong", "vivi", "num_hog"],
    ["cong", "vivi", "hog"],
]
YEAR_COLS = ["anio", "año", "ano", "year"]
SUFFIX_RE = re.compile(r"^(?P<base>.+)_(?P<yy>0[0-9]|1[0-9]|2[0-9])$")


def _anchor(cols_lower: dict) -> list[str]:
    for s in ANCHOR_SETS:
        got = [cols_lower[n] for n in s if n in cols_lower]
        if len(got) == len(s):
            return got
    for s in ANCHOR_SETS:
        got = [cols_lower[n] for n in s if n in cols_lower]
        if got:
            return got
    return []


def detect_layout(columns: list[str]) -> str:
    low = [c.lower() for c in columns]
    if any(y in low for y in YEAR_COLS):
        return "long"
    suf = [c for c in low if SUFFIX_RE.match(c)]
    return "wide" if len(suf) >= 10 else "flat"


def reshape_wide_to_long(df):
    """Melt _NN year-suffixed columns into a long panel with an `anio` column."""
    import pandas as pd
    cols_lower = {c.lower(): c for c in df.columns}
    anchors = _anchor(cols_lower)
    anchor_bases = {a.lower() for a in anchors}
    by_year: dict[str, dict[str, str]] = {}
    unsuffixed = []
    for c in df.columns:
        m = SUFFIX_RE.match(c.lower())
        # a suffixed copy of an anchor (e.g. conglome_19) would rename onto the
        # unsuffixed anchor and create a duplicate column -> skip it, the
        # unsuffixed anchor already carries the id across every wave
        if m and m.group("base") not in anchor_bases:
            by_year.setdefault(m.group("yy"), {})[m.group("base")] = c
        elif not m:
            unsuffixed.append(c)
    frames = []
    for yy, mapping in sorted(by_year.items()):
        sub = df[anchors + list(mapping.values())].copy()
        sub = sub.rename(columns={v: k for k, v in mapping.items()})
        sub["anio"] = 2000 + int(yy)
        for c in unsuffixed:
            if c not in anchors and c not in sub.columns:
                sub[c] = df[c].values
        frames.append(sub)
    return pd.concat(frames, ignore_index=True, sort=False)


def load_long(release_or_path, module: str | int = "sumaria",
              out: str | Path | None = None, download_if_missing: bool = True):
    """Load a panel module as a TIDY LONG panel: (df, meta).

    Accepts either a downloaded file path or (release, module) — in the latter
    case the file is downloaded first if missing. Detects the WIDE vs LONG
    physical layout and always returns long. meta carries the layout,
    longitudinal id columns, year column and wave list.
    """
    import pandas as pd
    if isinstance(release_or_path, (str, Path)) and Path(release_or_path).exists():
        p = Path(release_or_path)
    else:
        rel = int(release_or_path)
        p = path(rel, module, out)
        if not p.exists():
            if not download_if_missing:
                raise FileNotFoundError(p)
            download([rel], [module], out=out)
        if not p.exists():
            raise RuntimeError(f"could not obtain panel {rel} module {module}")

    df = _core.read_dta(p)
    layout = detect_layout(list(df.columns))
    cols_lower = {c.lower(): c for c in df.columns}

    if layout == "wide":
        df = reshape_wide_to_long(df)
        year_col = "anio"
    else:
        year_col = next((cols_lower[y] for y in YEAR_COLS if y in cols_lower), None)

    cl = {c.lower(): c for c in df.columns}
    id_cols = _anchor(cl)
    person = "codperso" in cl
    if person and cl["codperso"] not in id_cols:
        id_cols = id_cols + [cl["codperso"]]

    waves = []
    if year_col and year_col in df.columns:
        waves = sorted(int(v) for v in
                       pd.to_numeric(df[year_col], errors="coerce").dropna().unique())
    meta = {"layout": layout, "id_cols": id_cols, "year_col": year_col,
            "waves": waves, "person": person, "n_rows": len(df)}
    return df, meta
