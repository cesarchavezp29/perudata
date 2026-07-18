"""The ENAHO variable dictionary: every column of every module-year, from the
files INEI actually ships.

Built by reading the metadata of all 437 downloaded .dta files — 46,232 rows
(year x module x column) covering 5,052 distinct variables, each with INEI's own
variable label and value labels.

This exists so nobody has to guess-and-check a variable ever again:

    from perudata import dictionary as dic

    dic.find("analfab")              # which variable measures literacy?
    dic.variable("p302")             # which years is it in? does its label move?
    dic.value_labels("p203", 2025)   # what does code 0 mean?  -> 'Panel'
    dic.weights("85")                # what is the weight, per year?
    dic.changed_codes("p4195")       # did the coding change under a stable name?

The last two are the ones that catch silent errors. The expansion factor is
renamed across vintages (module 85 alone uses factor07 / facgob07 / famiegob07 /
facgob_p) and the coding of a variable can change while its name and label do
not (the health-insurance flags are 0/1 in 2004 and 1/2 from 2014).
"""
from __future__ import annotations

from importlib import resources

_DICT = None


def _load():
    global _DICT
    if _DICT is None:
        import pandas as pd
        with resources.files("perudata").joinpath(
                "catalogs/enaho_dictionary.csv.gz").open("rb") as f:
            _DICT = pd.read_csv(f, compression="gzip", encoding="utf-8",
                                dtype={"module": str, "column": str})
        # modules are two-digit strings ("01"), but a bare read turns "01" into
        # "1" for anything that round-tripped through a number. Normalize, or
        # every lookup for module "01" silently returns nothing.
        _DICT["module"] = _DICT["module"].astype(str).str.zfill(2)
    return _DICT


def all() -> "pd.DataFrame":  # noqa: A001,F821
    """The whole dictionary (year, module, column, label, value_labels, dtype)."""
    return _load().copy()


def find(term: str, in_label: bool = True):
    """Search variables by name OR by INEI's label. Returns one row per variable
    with the module and the year range it appears in."""
    d = _load()
    t = str(term).lower()
    hit = d["column"].str.lower().str.contains(t, na=False, regex=False)
    if in_label:
        hit = hit | d["label"].astype(str).str.lower().str.contains(
            t, na=False, regex=False)
    g = (d[hit].groupby(["module", "column"])
         .agg(label=("label", "first"), first_year=("year", "min"),
              last_year=("year", "max"), n_years=("year", "nunique"))
         .reset_index()
         .sort_values(["module", "column"]))
    return g


def variable(name: str):
    """Every appearance of one variable: which module, which years, what label.
    A label that MOVES across years is the first sign of a redefinition."""
    d = _load()
    return d[d["column"].str.lower() == str(name).lower()][
        ["year", "module", "label", "dtype", "value_labels"]].sort_values(
            ["module", "year"])


_OVERRIDES = None


def _load_overrides():
    """The verified value-label crosswalk: harmonized/corrected labels keyed by
    (module, column, year) -> {code: label}. This is where the package's own
    work lives -- INEI's .dta and dictionaries omit labels for post-2018 years,
    ship phantom codes, invert p407h, and label exhaustive batteries 'Pase'. The
    crosswalk fixes and fills all of that, and every row carries its evidence."""
    global _OVERRIDES
    if _OVERRIDES is None:
        import pandas as pd
        with resources.files("perudata").joinpath(
                "crosswalks/enaho_label_overrides.csv").open("rb") as f:
            o = pd.read_csv(f, encoding="utf-8-sig",
                            dtype={"module": str, "column": str, "code": str,
                                   "year": str, "label": str})
        o["module"] = o["module"].astype(str).str.zfill(2)
        idx, canon_raw = {}, {}
        for r in o.itertuples(index=False):
            idx.setdefault((r.module, r.column.lower(), r.year), {})[r.code] = r.label
            canon_raw.setdefault(
                (r.module, r.column.lower(), r.code), set()).add(r.label)
        # canonical casing: for a (module, column, code) whose crosswalk label is
        # the SAME concept in every year it covers (one label ignoring case), that
        # is the canonical spelling. A code the crosswalk genuinely RECODES across
        # years (>1 distinct label ignoring case, e.g. estrato) has no canonical
        # and is left per-year. Used only to unify casing, never to change meaning.
        canon = {}
        for k, labs in canon_raw.items():
            low = {x.lower() for x in labs}
            if len(low) == 1:
                canon[k] = sorted(labs)[0]
        _OVERRIDES = (idx, canon)
    return _OVERRIDES


def value_labels(name: str, year: int, module: str | None = None) -> dict:
    """What code N means for a variable in a given year, HARMONIZED.

    Starts from INEI's own parsed dictionary, then overlays the package's
    verified crosswalk so corrections win per code and gaps INEI never labelled
    (every year after ~2018, and battery/phantom cases) are filled. The crosswalk
    is the authoritative answer: it fixes INEI's own errors (e.g. p407h, whose
    .dta and dictionary invert 'attended'/'not attended') and each override
    carries the evidence that justifies it."""
    import json
    d = _load()
    q = (d["column"].str.lower() == str(name).lower()) & (d["year"] == int(year))
    if module:
        q &= d["module"] == str(module).zfill(2)
    labels: dict = {}
    for _, r in d[q].iterrows():
        if isinstance(r["value_labels"], str) and r["value_labels"]:
            labels = json.loads(r["value_labels"])
            break
    # overlay the verified crosswalk: a corrected/added label wins over INEI's.
    if module is not None:
        mod = str(module).zfill(2)
        col = str(name).lower()
        idx, canon = _load_overrides()
        ov = idx.get((mod, col, str(year)))
        if ov:
            # Drop any INEI code whose LABEL the crosswalk already carries at a
            # different code -- that is a stale encoding from the published PDF,
            # not a live code. p1145's 2006 dictionary lists code 5 'no tiene'
            # (the old single-variable form) while the released data is the {0,1}
            # flag the crosswalk describes; keeping code 5 would invent a
            # phantom. Dedup by normalized label so the crosswalk's code wins.
            def _norm(s: str) -> str:
                return "".join(ch for ch in str(s).lower() if ch.isalnum())
            ov_labels = {_norm(v) for v in ov.values()}
            labels = {k: v for k, v in labels.items()
                      if _norm(v) not in ov_labels}
            labels.update(ov)
        # Unify CASING across years. Where a year has no crosswalk row but the
        # .dta label is the same word as the crosswalk's canonical spelling for
        # that code (e.g. 'ocupado' vs 'Ocupado'), return the canonical so that
        # aggregating a pooled panel by label does not split the same category.
        # Codes the crosswalk genuinely recodes have no canonical and are kept.
        for k, v in list(labels.items()):
            c = canon.get((mod, col, str(k)))
            if c and c != v and c.lower() == str(v).lower():
                labels[k] = c
    return labels


def weights(module: str | int):
    """The expansion factor(s) this module ships, PER YEAR.

    The weight is renamed across vintages, so a hard-coded name silently loses it:
      * every module gains a SECOND weight in 2020 only — `factor_p`, the
        presencial (in-person) subsample of the COVID year, when ENAHO was partly
        conducted by telephone
      * modules 22-28/77 go factora0 (2010-2012) -> factora07 (2014-2025)
      * module 85 goes factor07 -> facgob07 -> famiegob07, plus facgob_p in 2020
    """
    d = _load()
    m = str(module).zfill(2)
    w = d[(d["module"] == m) &
          (d["label"].astype(str).str.contains("expansi", case=False, na=False) |
           d["column"].str.contains(r"^fac|^factor|^peso", case=False, na=False,
                                    regex=True))]
    return (w.groupby(["column", "label"])
            .agg(first_year=("year", "min"), last_year=("year", "max"),
                 n_years=("year", "nunique"))
            .reset_index().sort_values("first_year"))


def changed_codes(name: str):
    """Years in which a variable's VALUE LABELS changed — the silent-error hunter.

    A variable can keep its name and its label while INEI changes the coding
    underneath (health insurance is 0/1 in 2004 and 1/2 from 2014). This surfaces
    exactly that.
    """
    import json
    d = _load()
    rows = d[d["column"].str.lower() == str(name).lower()]
    out = []
    prev = None
    for _, r in rows.sort_values("year").iterrows():
        vl = json.loads(r["value_labels"]) if isinstance(r["value_labels"], str) \
            and r["value_labels"] else {}
        codes = tuple(sorted(vl.keys(), key=lambda k: float(k))) if vl else ()
        if codes != prev:
            out.append({"year": int(r["year"]), "module": r["module"],
                        "codes": ", ".join(f"{k}={vl[k]}" for k in codes) or "(none)",
                        "changed": prev is not None})
            prev = codes
    import pandas as pd
    return pd.DataFrame(out)
