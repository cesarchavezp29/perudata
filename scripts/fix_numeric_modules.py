"""Consumption/production modules: flag-battery 'Pase' -> 'No marcado', and one
contaminated label. Every change proven from the microdata before writing.

BACKGROUND. Modules 07-28, 77, 78 were newly resolved from INEI's published
dictionaries. Two defect classes surfaced, both already seen in the survey
modules, and both fixed here on the SAME evidence standard.

1. FLAG BATTERIES LABELLED 'Pase' AT CODE 0.

   These modules carry multiple-response batteries -- "¿cómo obtuvo el ...?"
   (acquisition), "¿cómo pagó?" (module 08), "¿qué tipo de explotación tiene?"
   (agro) -- split into per-code columns X_N holding {0, N}. Code 0 is
   'No marcado' (this way was not used), NOT 'Pase' (never asked): the item was
   obtained / the unit was paid for / the plot exists, just not via slot N.

   The resolver mislabelled code 0 as 'Pase' on the slots whose label names a
   code > 1 (rule 5, the multiple-response rule, fires only for {0,1}). The
   result was internally incoherent: module 22's p20001a code 0 = 'No marcado'
   while its SIBLINGS p20001b/p20001c = 'Pase', though all three are one
   battery. The data proves exhaustiveness -- across every year, essentially no
   in-universe row marks none of the siblings, and many mark two or more:

       acquisition p601a..p611a, p606e : markNONE <= 0.0006% of millions of rows
       payment     p602da/db/dc (m08)  : markNONE = 0,   mark2+ = 117
       exploitation p20001a/b/c (22-28): markNONE = 0,   mark2+ = tens of thousands

   The handful of all-zero rows (26 in module 07 across 22 years and ~15M
   records) is data-entry noise, not a 'not asked' category, which would be a
   structural share. So code 0 is 'No marcado' on every one.

2. A CONTAMINATED LABEL. Module 07 p601b code 1 was resolved as
   'Si         compraron o le regalaron alguno de los siguientes productos?' --
   the PDF->txt conversion ran the NEXT question's stem onto the value line and
   the parser swallowed it. INEI's .dta says code 1 is 'si'. The clean label is
   'Si'. This was the ONLY contaminated label in all 9,243 new rows (audited by
   verify_numeric_modules.py against INEI's own .dta).
"""
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parents[1]
XW = ROOT / "src" / "perudata" / "crosswalks" / "enaho_label_overrides.csv"

# (module, column-regex) -> the battery is proven exhaustive; code 0 = No marcado
BATTERIES = [
    ("07", r"p601a\d+"), ("09", r"p603a\d+"), ("10", r"p604a\d+"),
    ("11", r"p605a\d+"), ("12", r"p606a\d+"), ("13", r"p607a\d+"),
    ("16", r"p610a\d+"), ("17", r"p611a\d+"), ("78", r"p606e\d+"),
    ("08", r"p602d[abc]"),
    ("22", r"p20001[abc]"), ("23", r"p20001[abc]"), ("24", r"p20001[abc]"),
    ("25", r"p20001[abc]"), ("26", r"p20001[abc]"), ("27", r"p20001[abc]"),
    ("28", r"p20001[abc]"),
]

E_BATTERY = (
    "MULTIPLE-RESPONSE FLAG, proven exhaustive by the battery's own data. {col} "
    "is one slot of a battery split into per-code columns X_N holding {{0, N}}. "
    "Across every year, essentially no in-universe row marks none of the "
    "siblings (markNONE <= 0.0006% of the rows) and many mark two or more, so a "
    "code-0 cell always belongs to a record that answered by marking a different "
    "slot -- 'No marcado', not 'Pase' (never asked). The earlier 'Pase' came "
    "from code 0 sitting inside the dictionary's declared range; the range proves "
    "the code EXISTS, not that it means 'not applicable'. The sibling slot whose "
    "label names code 1 was already 'No marcado'; this makes the whole battery "
    "coherent."
)


def main() -> int:
    o = pd.read_csv(XW, encoding="utf-8-sig", dtype=str)

    total = 0
    for mod, rx in BATTERIES:
        m = ((o.module == mod) & o.column.str.fullmatch(rx, na=False)
             & (o.code == "0") & (o.label == "Pase"))
        n = int(m.sum())
        if not n:
            continue
        o.loc[m, "label"] = "No marcado"
        o.loc[m, "evidence"] = [E_BATTERY.format(col=c) for c in o.loc[m, "column"]]
        total += n
        print(f"  {mod} {rx:<12}: {n} rows 'Pase' -> 'No marcado'")

    # the single contaminated label
    c = (o.module == "07") & (o.column == "p601b") & (o.code == "1")
    was = set(o.loc[c, "label"])
    o.loc[c, "label"] = "Si"
    o.loc[c, "evidence"] = (
        "CORRECTS A DICTIONARY-PARSE CONTAMINATION. The 2023 dictionary ran the "
        "next question's stem onto p601b's value line ('1. Si  compraron o le "
        "regalaron alguno...'), and the parser took the whole run as the label. "
        "INEI's own .dta says code 1 is 'si'; the clean label is 'Si', matching "
        "every other year of this column.")
    print(f"  07 p601b code 1  : {was} -> 'Si'")

    o.to_csv(XW, index=False, encoding="utf-8")

    chk = pd.read_csv(XW, encoding="utf-8-sig", dtype=str)
    for mod, rx in BATTERIES:
        bad = chk[(chk.module == mod) & chk.column.str.fullmatch(rx, na=False)
                  & (chk.code == "0") & (chk.label == "Pase")]
        assert bad.empty, f"{mod} {rx}: {len(bad)} rows still 'Pase'"
    assert (chk[(chk.module == "07") & (chk.column == "p601b")
                & (chk.code == "1")].label == "Si").all()
    assert not chk.label.astype(str).str.contains("compraron").any(), "contamination remains"
    print(f"\nfixed {total} battery rows + 1 contaminated label")
    return 0


if __name__ == "__main__":
    sys.exit(main())
