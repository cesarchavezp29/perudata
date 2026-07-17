"""Modules 01/02/04: fix what is proven, and LEAVE what only looked wrong.

Two of the four alarms here turned out to be the shipped label being RIGHT and
the recomputed one wrong. Recording both outcomes, because the near-misses are
the point: any blanket rule -- "new wins", "dictionary wins" -- would have
corrupted real analytical variables.

FIXED
-----
1. p1145 code 1: 'Telefono fijo' -> 'No tiene'   (2006, 2007)

   p1145 is the "household has NONE of these" slot of the p114x battery
   (telefono fijo / celular / TV cable / internet). The 2006-2007 rows carry
   p1141's label instead, so 13,479 households in 2006 and 11,736 in 2007 that
   own NO service at all are labelled landline owners.

   INEI's own .dta says 'no tiene' in every year it labels the column (2004,
   2012, 2024), the dictionary agrees ("P1145 ... Su hogar no tiene: Telefono
   fijo, celular, TV cable, Internet / 1.No tiene"), and the data proves it
   deterministically:

       p1145 == 1  ->  owns ANY of p1141-p1144 in   0.0% of rows
       p1145 == 0  ->  owns ANY of p1141-p1144 in 100.0% of rows

   in 2006, 2007, 2012 and 2024 alike. Exact complementarity, no exceptions.

2. p107a14/24/34 code 1: 'Si' -> 'No gasto <ampliacion|modificacion|
   construccion nueva>'

   These are not the "did you spend?" question -- that is p107a11/21/31, whose
   label {0: 'no', 1: 'si'} leaked one slot over. p107aN4 is a follow-up flag
   marking "no gasto" AMONG households that reported the activity, which the
   data confirms exactly:

       p107a14 == 1  ->  100.0% also have p107a11 == 1   (n=59 of 1,271 in 2007)
       p107a24 == 1  ->  100.0% also have p107a21 == 1
       p107a34 == 1  ->  100.0% also have p107a31 == 1

   in 2007, 2008 and 2010. INEI's 2008 .dta names them outright:
   {'1': 'no gasto ampliacion'}, {'1': 'no gasto modificacion'},
   {'1': 'no gasto construccion nueva'}.

NOT FIXED -- the shipped label was right and the "correction" was wrong
-----------------------------------------------------------------------
3. p407h code 1 stays 'No lo atendieron'.

   INEI's dictionary and .dta CONTRADICT each other outright:
       dictionary: 0 No lo atendieron / 1 Si lo atendieron
       .dta      : 0 si lo atendieron / 1 no lo atendieron
   The data settles it against the dictionary. p407h1/p407h2 record the hours
   and minutes waited:
       code 1 (n=302)    -> nonzero wait in   0.0% of rows
       code 0 (n=19,351) -> nonzero wait in  68.9%, median 5 minutes
   Someone who was not attended cannot have waited a time, and code 1 is 1.5%
   of consultations, which is the plausible share for "they did not attend me".
   A "dictionary wins" rule would have INVERTED a health-access variable.

4. p208a1 code 0 stays 'No nacio en este distrito' (not 'Pase').

   p208a2 records the district of birth:
       code 1 -> birth district == home district in 100.0% of 70,606 rows
       code 0 -> birth district == home district in   0.0% of 63,629 rows
   Zero mismatches in 134,235 rows. Code 0 is the substantive "no", and 47% of
   respondents cannot be a `pase` on a question asked of everyone.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parents[1]
OUT = ROOT / "src" / "perudata" / "crosswalks" / "enaho_label_overrides.csv"

E_1145 = (
    "CORRECTS A BATTERY-POSITION LEAK, PROVEN BY EXACT COMPLEMENTARITY. p1145 is "
    "the 'household has NONE of these' slot of the p114x battery, but this row "
    "carried p1141's label ('Telefono fijo'), calling 13,479 households in 2006 "
    "and 11,736 in 2007 landline owners when they own no service at all. INEI's "
    "own .dta says 'no tiene' in every year it labels the column (2004, 2012, "
    "2024) and the dictionary agrees ('Su hogar no tiene: Telefono fijo, celular, "
    "TV cable, Internet / 1.No tiene'). The data is deterministic: p1145==1 owns "
    "ANY of p1141-p1144 in 0.0% of rows, p1145==0 in 100.0%, with no exceptions "
    "in 2006, 2007, 2012 or 2024."
)


def e_107(what: str) -> str:
    return (
        f"CORRECTS A BATTERY-POSITION LEAK. This slot is NOT the 'did you spend?' "
        f"question -- that is p107a11/21/31, whose label {{0: 'no', 1: 'si'}} "
        f"leaked one slot over. p107aN4 flags 'no gasto {what}' AMONG households "
        f"that reported the activity, which the data confirms exactly: code 1 is "
        f"100.0% a subset of the matching p107aN1==1 filter in 2007, 2008 and "
        f"2010. INEI's own 2008 .dta names this code 'no gasto {what}'."
    )


FIX = {
    ("p1145", "1"): ("No tiene", E_1145),
    ("p107a14", "1"): ("No gasto ampliacion", e_107("ampliacion")),
    ("p107a24", "1"): ("No gasto modificacion", e_107("modificacion")),
    ("p107a34", "1"): ("No gasto construccion nueva", e_107("construccion nueva")),
}

# proven correct as shipped -- must NOT drift back to the "corrected" value
KEEP = {
    ("p407h", "1"): "No lo atendieron",
    ("p208a1", "0"): "No nacio en este distrito",
}


def main() -> int:
    o = pd.read_csv(OUT, encoding="utf-8-sig", dtype=str)
    total = 0
    for (col, code), (label, ev) in FIX.items():
        hit = (o.column == col) & (o.code == code)
        if not hit.any():
            print(f"  {col} code {code}: NO ROWS"); continue
        was = o.loc[hit, "label"].value_counts().to_dict()
        n = int((hit & (o.label != label)).sum())
        o.loc[hit, "label"] = label
        o.loc[hit, "evidence"] = ev
        total += n
        print(f"  {col:<9} code {code}: {was} -> {label!r}  ({n} rows)")
    o.to_csv(OUT, index=False, encoding="utf-8")

    chk = pd.read_csv(OUT, encoding="utf-8-sig", dtype=str)
    for (col, code), (label, _) in FIX.items():
        got = set(chk[(chk.column == col) & (chk.code == code)].label.dropna())
        assert got <= {label}, f"{col} code {code} still {got}"
    print(f"\ncorrected {total} rows")
    for (col, code), want in KEEP.items():
        got = set(chk[(chk.column == col) & (chk.code == code)].label.dropna())
        print(f"  left alone (proven right as shipped): {col} code {code} = {got}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
