"""Every carry-forward row CITES its source years. Do those years actually say it?

A carry-forward row makes a checkable claim in its own evidence string:

    "2007 ships no label for p5291c code 0, but INEI labels that exact code on
     that exact variable in [2004, 2005, 2006, 2013] as 'pase'."

That names the years it copied FROM. So the claim is falsifiable without any
microdata at all: look up what those same years say for that same (column, code)
and see whether they say 'pase'. They do not -- the crosswalk's own 2004, 2005,
2006 and 2013 rows for p5291c code 0 all read 'Sabe', which is also what INEI's
2004 .dta value label says ({0: 'sabe'}) and what the 2007 published dictionary
says ('P5291C ... 0 Sabe', for a variable literally named "Indicador no sabe").

So the row asserts INEI's testimony while contradicting it, and cites as proof
the very years that refute it. These are stale rows from an older, buggier
resolver run: the merge was append-only (concat([old, new], keep="first")), so a
wrong row written once could never be superseded by the rule that fixed it.

This audit is cheap and total: no downloads, no rules, no heuristics. It only
asks whether the file is CONSISTENT WITH ITSELF. Any row whose cited years
contradict its own label is unsafe -- report every one, fix none automatically,
because "the citation is wrong" does not by itself say which label is right.
"""
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parents[1]
OUT = ROOT / "src" / "perudata" / "crosswalks" / "enaho_label_overrides.csv"

CITES = re.compile(r"in \[([0-9,\s]+)\] as '(.*?)'", re.S)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())


def main() -> int:
    o = pd.read_csv(OUT, encoding="utf-8-sig", dtype=str)
    # label actually shipped for each (module, column, code, year)
    have = {}
    for r in o.itertuples(index=False):
        have[(r.module, r.column, r.code, str(r.year))] = r.label

    bad = []
    checked = 0
    for r in o.itertuples(index=False):
        m = CITES.search(str(r.evidence))
        if not m:
            continue
        years = [y.strip() for y in m.group(1).split(",") if y.strip()]
        claimed = m.group(2)
        checked += 1
        # 1. does the row's own label match what it claims INEI said?
        self_ok = norm(claimed) == norm(r.label)
        # 2. do the cited years actually carry that label?
        says = {}
        for y in years:
            v = have.get((r.module, r.column, r.code, y))
            if v is not None:
                says[y] = v
        if not says:
            continue
        agree = [y for y, v in says.items() if norm(v) == norm(claimed)]
        if not agree:
            bad.append({
                "module": r.module, "column": r.column, "code": r.code,
                "year": r.year, "label": r.label, "claimed": claimed,
                "cited_years": ",".join(years),
                "cited_years_actually_say": "|".join(
                    f"{y}={v}" for y, v in sorted(says.items())),
                "self_consistent": self_ok,
            })

    print(f"carry-forward rows making a citable claim : {checked:,}")
    print(f"rows whose CITED YEARS REFUTE the claim   : {len(bad):,}")
    if not bad:
        print("\nthe crosswalk is consistent with its own citations")
        return 0

    d = pd.DataFrame(bad)
    p = ROOT / "scripts" / "carryforward_contradictions.csv"
    d.to_csv(p, index=False, encoding="utf-8")
    print(f"\nwrote {p}")
    print(f"\naffected columns: {d.column.nunique()}  "
          f"(modules {sorted(d.module.unique())})")
    print("\nworst offenders:")
    g = d.groupby(["module", "column", "code", "label", "claimed"]).agg(
        rows=("year", "size"),
        cited_say=("cited_years_actually_say", "first")).reset_index()
    g = g.sort_values("rows", ascending=False)
    for r in g.head(14).itertuples(index=False):
        print(f"  {r.module} {r.column:<11} code {r.code:<3} shipped={r.label[:26]!r:<28} "
              f"claims INEI said {r.claimed[:20]!r:<22} ({r.rows} rows)")
        print(f"      but cited years say: {r.cited_say[:96]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
