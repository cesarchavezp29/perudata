"""One call, one harmonized dataset.

    from perudata import dataset

    df = dataset(range(2019, 2026), "34", "02", harmonize=True)

Give it a span of years and the modules you want. It downloads what is missing,
normalizes the join keys, merges the modules on the correct key and universe,
applies the crosswalks, and stacks every year into ONE table with a stable
schema — so a variable absent in some vintage comes back as an all-NA column
that is MARKED, never a missing column that breaks the pool.

What it will not do quietly:
  * it never inner-joins modules with different universes (one anchor defines the
    universe, everything else LEFT-joins onto it, and the misses are reported)
  * it never rescales money (harmonization renames and recodes only)
  * a year it cannot fetch is recorded as unfetched and the rest still returns
"""
from __future__ import annotations

from pathlib import Path

from . import _core, enaho


def _years(spec) -> list[int]:
    if isinstance(spec, int):
        return [spec]
    if isinstance(spec, range):
        return list(spec)
    if isinstance(spec, tuple) and len(spec) == 2 and all(
            isinstance(x, int) for x in spec):
        return list(range(spec[0], spec[1] + 1))     # (2019, 2025) inclusive
    return [int(y) for y in spec]


def dataset(years, *modules, harmonize: bool = True, level: str = "auto",
            survey: str = "enaho", anchor: str | None = None,
            out: str | Path | None = None, verbose: bool = True):
    """Build ONE harmonized, multi-year, multi-module table.

    years   : 2024 | [2019, 2024] | range(2019, 2026) | (2019, 2025) inclusive
    modules : "34", "02", ... (household and/or person level)
    level   : "auto" (person if a person module is present, else household)
    anchor  : module whose universe defines the rows (default: 34 / 02)

    Returns a DataFrame. df.attrs carries:
      "years_ok", "unfetched"  — which years made it in, and why any did not
      "coverage"               — per year x canonical variable: resolved? from
                                 which raw name? if not, why not
      "combine"                — the join report for each year
    """
    import pandas as pd

    if survey != "enaho":
        raise NotImplementedError(
            f"dataset() covers ENAHO today. {survey!r} has no crosswalk yet — "
            f"use the survey module directly ({survey}.load(...)).")

    mods = [str(m).zfill(2) for m in (modules or ("34",))]
    ys = _years(years)
    if level == "auto":
        level = "person" if any(m in enaho.PERSON_MODULES for m in mods) \
            else "household"

    frames, coverage, joins, unfetched, ok = [], [], {}, [], []
    for y in ys:
        try:
            d = enaho.combine(y, mods, level=level, out=out, anchor=anchor,
                              harmonize=harmonize)
        except _core.PerudataError as e:
            # a year that cannot be fetched must not kill the pool
            unfetched.append({"year": y, "error": type(e).__name__, "detail": str(e)})
            if verbose:
                print(f"[warn] {y}: {type(e).__name__} — skipped, pool continues")
            continue
        if "year" not in d.columns:
            d["year"] = y
        d["year"] = pd.to_numeric(d["year"], errors="coerce").fillna(y).astype(int)
        joins[y] = d.attrs.get("combine")
        for rec in d.attrs.get("coverage", []):
            coverage.append({"year": y, **rec})
        frames.append(d)
        ok.append(y)
        if verbose:
            print(f"[ok  ] {y}: {len(d):,} rows x {d.shape[1]} cols")

    if not frames:
        raise RuntimeError(f"no year could be built (unfetched: {unfetched})")

    # STABLE SCHEMA: union of columns, so a variable absent in one vintage is an
    # all-NA column in that year rather than a column that vanishes from the pool
    cols: list[str] = []
    for f in frames:
        for c in f.columns:
            if c not in cols:
                cols.append(c)
    frames = [f.reindex(columns=cols) for f in frames]
    pool = pd.concat(frames, ignore_index=True, sort=False)

    # carry the per-column stability status through to the pooled frame, and
    # SAY OUT LOUD which columns cannot be pooled blindly
    unsafe: list[str] = []
    for f in frames:
        unsafe += [c for c in f.attrs.get("unsafe_columns", []) if c in pool.columns]
    pool.attrs["unsafe_columns"] = sorted(set(unsafe))
    pool.attrs["years_ok"] = ok
    pool.attrs["unfetched"] = unfetched
    pool.attrs["coverage"] = coverage
    pool.attrs["combine"] = joins
    pool.attrs["harmonized"] = harmonize
    if verbose:
        print(f"\npooled: {len(pool):,} rows x {pool.shape[1]} cols, "
              f"years {min(ok)}-{max(ok)} ({len(ok)} of {len(ys)})")
        if unfetched:
            print(f"unfetched: {[u['year'] for u in unfetched]}")
        n_unsafe = len(pool.attrs.get("unsafe_columns", []))
        if n_unsafe:
            print(f"WARNING: {n_unsafe} of {pool.shape[1]} columns change their "
                  f"coding, their question or their coverage across these years — "
                  f"see df.attrs['unsafe_columns'] and harmonize.unsafe(module).")
    return pool
