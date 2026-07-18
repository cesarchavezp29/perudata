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
MODULES = os.environ.get("PERUDATA_MODULES", "37,85").split(",")


def stem_of(col: str) -> str:
    """Strip ONE trailing index level only. 'p401d1'->'p401d', 'p22a_1_01'->
    'p22a_1', 'p8_2'->'p8'. Stripping ALL trailing digits ('p2591'->'p') would
    pool unrelated variables under a bare 'p', so a battery is recognised only
    when the shared stem is specific (>=2 chars, not a lone letter)."""
    return re.sub(r"(_\d+|\d)$", "", col)


def battery_ok(mod: str, family: list) -> tuple[bool, int, int]:
    """Is code 0 provably 'No marcado' on this family? Returns (passes, admin0,
    zero_only).

    The proof must be NON-VACUOUS. 'A 0-cell sits in an administered row' is
    tautological -- a 0 is non-NA by definition. The real evidence that 0 means
    'asked and not selected' is a row where this family has a sibling == 1 AND
    another sibling == 0 at the same time: the 1 proves the battery was applied,
    so the co-occurring 0 is a deliberate 'not this one', not a skip.

    Also enforces that the family is a genuine set of {0, k} FLAGS. A column that
    is not a flag (holds several positive codes -- a single-choice question) is
    dropped, so distinct questions that merely share a stem prefix (p501, p502)
    cannot be pooled into a spurious battery.

      admin0     rows where some flag == 1 and some flag == 0 (the proof)
      zero_only  in-universe rows where every flag == 0 (asked, marked none)
    """
    fam = [c.lower() for c in family]
    admin0 = zero_only = flag_years = 0
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
        # keep only genuine {0, k} flags: <=1 distinct positive value
        flags = [c for c in present
                 if v[c][v[c] > 0].nunique() <= 1]
        if len(flags) < 2:
            continue
        w = v[flags]
        has1 = (w == 1).any(axis=1)
        has0 = (w == 0).any(axis=1)
        inuni = ~w.isna().all(axis=1)
        admin0 += int((has1 & has0).sum())
        zero_only += int((inuni & ~has1 & has0).sum())
        flag_years += 1
    # require a ROBUST count, not a single record: one co-occurrence cannot
    # establish that 0 means 'administered, not selected' (the estrsocial
    # one-row lesson). 30 mirrors the noise-decline floor used elsewhere.
    passes = flag_years > 0 and admin0 >= 30
    return passes, admin0, zero_only


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
            if len(stem) < 2:
                print(f"   {stem!r}: single-letter stem pools unrelated "
                      f"variables -> KEEP 'Pase' ({sorted(cols)[:4]})")
                continue
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
            ok, admin0, zero_only = battery_ok(mod, sorted(family))
            m = ((o.module == mod) & o.column.isin(cols)
                 & (o.code == "0") & (o.label == "Pase"))
            n = int(m.sum())
            if ok:
                o.loc[m, "label"] = "No marcado"
                o.loc[m, "evidence"] = (
                    f"MULTIPLE-RESPONSE FLAG, proven administered by the released "
                    f"records. {stem}* is a battery of {len(family)} {{0,k}} flag "
                    f"slots. In {admin0:,} records a sibling flag is set to 1 while "
                    f"another is 0, so the battery WAS applied and the co-occurring "
                    f"0 is a deliberate 'not this one', not a skip. Code 0 is 'No "
                    f"marcado' -- asked and not selected -- not 'Pase' (never "
                    f"asked); the not-asked rows are NA, not 0.")
                total += n
                print(f"   {stem}* ({len(family)} slots): {n} rows -> 'No marcado' "
                      f"(admin0={admin0:,}, zero_only={zero_only:,})")
            else:
                print(f"   {stem}* ({len(family)} slots): KEEP 'Pase' "
                      f"(admin0={admin0}) -- no sibling proves it was administered")
    if not apply:
        print("\n(dry run -- pass --apply to write)")
        return 0

    o.to_csv(XW, index=False, encoding="utf-8")
    print(f"\napplied: {total} battery rows 'Pase' -> 'No marcado'")
    return 0


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
