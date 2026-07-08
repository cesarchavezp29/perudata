"""
Validation gate: reproduce INEI's OFFICIAL published statistics from the raw
microdata, so you can trust the pipeline before building anything on top.

National monetary poverty is computed Sumaria-only (module 34): poverty and
income are HOUSEHOLD concepts and the sumaria already carries pobreza,
factor07 and mieperho, so no module merge is needed and no person is ever
dropped.

INEI official method:
  * unit of poverty = PERSON
  * person weight   = factor07 (household expansion) x mieperho (household size)
  * poor            = pobreza in {1, 2}   (1=extreme, 2=non-extreme)
  * extreme poor    = pobreza == 1

    from perudata import validate
    table = validate.poverty(years=[2023, 2024])   # downloads sumaria if needed
"""
from __future__ import annotations

from pathlib import Path

from . import enaho

# INEI official monetary poverty headcount, national, % of population
# (current-methodology series, Informe "Evolución de la Pobreza Monetaria")
OFFICIAL_POVERTY = {
    2004: 58.7, 2005: 55.6, 2006: 49.1, 2007: 42.4, 2008: 37.3, 2009: 33.5,
    2010: 30.8, 2011: 27.8, 2012: 25.8, 2013: 23.9, 2014: 22.7, 2015: 21.8,
    2016: 20.7, 2017: 21.7, 2018: 20.5, 2019: 20.2, 2020: 30.1, 2021: 25.9,
    2022: 27.5, 2023: 29.0, 2024: 27.6, 2025: 25.7,
}
OFFICIAL_EXTREME = {2020: 5.1, 2021: 4.1, 2022: 5.0, 2023: 5.7, 2024: 5.5, 2025: 4.7}


def poverty_year(year: int, out: str | Path | None = None) -> dict | None:
    """National poverty for one year straight from the raw sumaria."""
    df = enaho.load(year, "34", out=out,
                    columns=None)  # columns differ by vintage; filter after load
    need = {"pobreza", "factor07", "mieperho"}
    if not need.issubset(df.columns):
        return None
    df = df.dropna(subset=["pobreza", "factor07", "mieperho"])
    w = df["factor07"] * df["mieperho"]
    pov = 100 * w[df["pobreza"].isin([1, 2])].sum() / w.sum()
    ext = 100 * w[df["pobreza"] == 1].sum() / w.sum()
    return {
        "year": year,
        "n_households": len(df),
        "population_wtd": round(w.sum()),
        "poverty_pct": round(pov, 1),
        "official_poverty": OFFICIAL_POVERTY.get(year),
        "extreme_pct": round(ext, 1),
        "official_extreme": OFFICIAL_EXTREME.get(year),
    }


def poverty(years: list[int] | None = None, out: str | Path | None = None,
            verbose: bool = True):
    """Reproduce the official national poverty series. Returns a DataFrame with
    the computed rate, the official rate and their difference per year."""
    import pandas as pd
    years = years or enaho.years()
    rows = []
    for y in years:
        r = poverty_year(y, out=out)
        if r:
            rows.append(r)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["pov_diff"] = (df["poverty_pct"] - df["official_poverty"]).round(1)
    df["ext_diff"] = (df["extreme_pct"] - df["official_extreme"]).round(1)
    if verbose:
        matched = df.dropna(subset=["official_poverty"])
        within = (matched["pov_diff"].abs() <= 0.1).sum()
        print(df.to_string(index=False))
        print(f"\nNational poverty reproduced within 0.1pp of INEI in "
              f"{within}/{len(matched)} years.")
    return df
