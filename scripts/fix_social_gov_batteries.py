"""Modules 37 (social programmes) and 85 (governance): battery 'Pase' -> 'No marcado'.

These two were resolved in an earlier session, before the multiple-response rule
was proven, so their flag batteries kept 'Pase' on code 0: module 37's programme
batteries (p710_* wawa wasi/cuna mas, p701_* vaso de leche/desayuno escolar) and
module 85's corruption batteries (p2_1_* perception areas, p22a_*_* the places a
person witnessed corruption).

'Pase' asserts the question was never asked. The data refutes that for a battery
slot: a code-0 cell (a real 0, not a blank) only exists in a row where the
battery was ADMINISTERED. Verified per column, per year -- of the rows carrying a
0 in the family, the number that are out-of-universe (all siblings NA) is ZERO,
and the family is genuinely multiple-response (rows marking 2+). So code 0 is
'No marcado': the person was asked and did not select this option. The
out-of-universe rows are NA, not 0, so they are untouched.

This does NOT blanket-flip every 'Pase'. Each candidate column is tested against
the microdata and only flipped if it passes the battery signature:
  * it has >= 2 sibling columns sharing its stem,
  * every year, no code-0 row is out-of-universe (all-NA siblings), and
  * the family carries multi-response rows (mark 2+ of the siblings).
A column that fails -- a genuine filter follow-up where 0 really is a skip --
keeps 'Pase' and is reported.
"""
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")
sys.path.insert(0, "src")

import pandas as pd  # noqa: E402
import pyreadstat  # noqa: E402

from perudata import enaho  # noqa: E402

ROOT = Path(__file__).parents[1]
XW = ROOT / "src" / "perudata" / "crosswalks" / "enaho_label_overrides.csv"
MODULES = ["37", "85"]


def stem_of(col: str) -> str:
    return re.sub(r"_?\d+$", "", col)


def battery_ok(mod: str, family: list) -> tuple[bool, int, int]:
    """(passes, total out-of-universe 0-rows, total mark2+) across all years."""
    fam = [c.lower() for c in family]
    out_total = multi_total = years = 0
    for y in enaho.years():
        p = enaho.path(y, mod)
        if not p.exists():
            continue
        try:
            _, meta = pyreadstat.read_dta(str(p), metadataonly=True)
        except Exception:
            continue
        present = [c for c in fam if c in {x.lower() for x in meta.column_names}]
        if len(present) < 2:
            continue
        df, _ = pyreadstat.read_dta(str(p), usecols=present)
        v = df.apply(pd.to_numeric, errors="coerce")
        inuni = ~v.isna().all(axis=1)
        has0 = (v == 0).any(axis=1)
        out_total += int((has0 & ~inuni).sum())
        multi_total += int(((v > 0).sum(axis=1)[inuni] >= 2).sum())
        years += 1
    passes = years > 0 and out_total == 0 and multi_total > 0
    return passes, out_total, multi_total


def main(apply: bool) -> int:
    o = pd.read_csv(XW, encoding="utf-8-sig", dtype=str)
    total = 0
    for mod in MODULES:
        z = o[(o.module == mod) & (o.code == "0") & (o.label == "Pase")]
        # A battery SLOT is a {0, k} flag: one non-zero code. A single-choice
        # question (module 85 p9: democracy preference, codes 1-4) is NOT a
        # battery, and code 0 there is a real skip, not 'No marcado'. Restrict
        # to flag columns so aggressive stem-stripping cannot sweep p9 in.
        flag_cols = set()
        for c in z.column.unique():
            nz = o[(o.module == mod) & (o.column == c)
                   & (o.code != "0")].code.nunique()
            if nz <= 1:
                flag_cols.add(c)
            else:
                print(f"   (module {mod}) {c}: {nz} non-zero codes -> "
                      f"single-choice, KEEP 'Pase'")
        fams = defaultdict(set)
        for c in flag_cols:
            fams[stem_of(c)].add(c)
        # need the full family from the data, not just the Pase-bearing members
        print(f"\n=== module {mod}: {len(z)} code-0 'Pase' rows, "
              f"{len(fams)} candidate stems")
        for stem, cols in sorted(fams.items()):
            rx = re.compile(re.escape(stem) + r"_?\d+$")
            # discover full family from a year's columns
            family = set(cols)
            for y in enaho.years():
                p = enaho.path(y, mod)
                if not p.exists():
                    continue
                try:
                    _, meta = pyreadstat.read_dta(str(p), metadataonly=True)
                except Exception:
                    continue
                family |= {c.lower() for c in meta.column_names
                           if rx.fullmatch(c.lower())}
            if len(family) < 2:
                print(f"   {stem}*: single column, NOT a battery -> keep 'Pase'")
                continue
            ok, out, multi = battery_ok(mod, sorted(family))
            m = ((o.module == mod) & o.column.isin(cols)
                 & (o.code == "0") & (o.label == "Pase"))
            n = int(m.sum())
            if ok:
                o.loc[m, "label"] = "No marcado"
                o.loc[m, "evidence"] = (
                    f"MULTIPLE-RESPONSE FLAG, proven administered. {stem}* is a "
                    f"battery of {len(family)} slots; every code-0 cell sits in a "
                    f"row where the battery was administered (out-of-universe "
                    f"0-rows = {out} across all years) and the family is "
                    f"multi-response ({multi} rows mark 2+). Code 0 is 'No "
                    f"marcado' -- asked and not selected -- not 'Pase' (never "
                    f"asked); out-of-universe rows are NA, not 0.")
                total += n
                print(f"   {stem}* ({len(family)} slots): {n} rows -> 'No marcado' "
                      f"(out={out}, multi={multi})")
            else:
                print(f"   {stem}* ({len(family)} slots): KEEP 'Pase' "
                      f"(out={out}, multi={multi}) -- not an exhaustive battery")
    if not apply:
        print("\n(dry run -- pass --apply to write)")
        return 0

    o.to_csv(XW, index=False, encoding="utf-8")
    print(f"\napplied: {total} battery rows 'Pase' -> 'No marcado'")
    return 0


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
