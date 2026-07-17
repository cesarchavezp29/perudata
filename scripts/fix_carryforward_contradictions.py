"""Three columns whose shipped label is refuted by the crosswalk's own citations.

Each row here was adjudicated on its own evidence. Note that the answer went a
DIFFERENT WAY for r559 than for p5291c/p530b -- which is exactly why no source
ranking and no "prefer the newer rule" could have fixed these. INEI errs in the
.dta sometimes and in the dictionary other times.

1. p5291c code 0 -> 'Sabe'   (was 'Pase', 18 rows)
2. p530b  code 0 -> 'Tiene ganancia' (was 'Pase', 18 rows)

   The shipped rows say 'Pase' for 2007-2025 while the SAME FILE says 'Sabe' /
   'Tiene ganancia' for 2004, 2005, 2006 and 2013 -- and the 'Pase' rows cite
   exactly those four years as their proof:

       "INEI labels that exact code on that exact variable in
        [2004, 2005, 2006, 2013] as 'pase'"

   which is false against the years it names. Five independent proofs agree the
   label is 'Sabe' / 'Tiene ganancia':
     * the 2007 published dictionary: "P5291C ... 0 Sabe / 1 No sabe, Rango 0-1"
       and "P530B ... 0 Tiene ganancia / 1 No sabe/no tiene ganancia"
     * INEI's own 2004 and 2005 .dta value labels: {0: 'sabe', 1: 'no sabe'} and
       {0: 'tiene ganancia', 1: 'no sabe/no tiene ganancia'}
     * the crosswalk's own 2004/2005/2006/2013 rows
     * the variable's name: "Indicador no sabe si recibe por alimentos" -- a
       no-sabe INDICATOR, so code 0 is the affirmative "Sabe"
     * the declared range 0-1 with BOTH codes substantive, leaving no room for a
       `pase`: 'Pase' would assert the question was never asked, of a variable
       whose entire purpose is to record whether the person knew.

3. r559_* code 9 -> 'Otros'  (2013-2016 rows said 'Cena')

   Here the DICTIONARY is the one that errs, and the shipped 'Otro' was right.
   The 2013-2016 dictionaries say "9.Cena"; 2017-2019 say "9. Otros"; and 2020
   lists BOTH "3.Cena" and "9. Otros", showing they are distinct codes. INEI's
   own 2012/2013 .dta says 9 = 'otros alimentos y bebidas'.

   The data settles it. Code 9 carries ~80% of the mass in 2013-2017:

       2013-2017 (15 cols)   1: 7%   2: 13%          9: 80%
       2019-2022 (50 cols)   1: 18%  2: 33%   3: 8%  9: 37-45%

   Dinner cannot be 80% of meals eaten outside the home while breakfast is 7%
   and lunch 13%. And once Cena gets its own code in 2019+, it is ~8% -- so
   reading 9 as 'Cena' would have dinners collapse from 80% to 8% in the year a
   code was added, with no change to the questionnaire's meaning. Code 9 is the
   catch-all, exactly as INEI's .dta says.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parents[1]
OUT = ROOT / "src" / "perudata" / "crosswalks" / "enaho_label_overrides.csv"

E_SABE = (
    "CORRECTS A STALE, SELF-REFUTING ROW. The shipped 'Pase' cited [2004, 2005, "
    "2006, 2013] as proof, but those years label this code 'Sabe' in this very "
    "file, in INEI's own 2004/2005 .dta ({0: 'sabe'}), and in the 2007 published "
    "dictionary ('P5291C ... 0 Sabe / 1 No sabe, Rango: 0 - 1'). The variable is "
    "named 'Indicador no sabe si recibe por alimentos' -- a no-sabe indicator, so "
    "code 0 is the affirmative 'Sabe'. Both codes are substantive within the "
    "declared range 0-1, leaving no room for a `pase`."
)
E_GAN = (
    "CORRECTS A STALE, SELF-REFUTING ROW. The shipped 'Pase' cited [2004, 2005, "
    "2006, 2013] as proof, but those years label this code 'Tiene ganancia' in "
    "this very file, in INEI's own 2004/2005 .dta ({0: 'tiene ganancia'}), and in "
    "the 2007 published dictionary ('P530B ... 0 Tiene ganancia / 1 No sabe/no "
    "tiene ganancia, Rango: 0 - 1'). The variable is named 'Indicador de ganancia "
    "neta independiente'. Both codes are substantive, leaving no room for a `pase`."
)
E_OTROS = (
    "THE DICTIONARY IS WRONG, NOT THE DATA. The 2013-2016 dictionaries label "
    "r559 code 9 as 'Cena', but 2017-2019 say 'Otros' and 2020 lists '3.Cena' AND "
    "'9. Otros' as separate codes -- and INEI's own 2012/2013 .dta says 9 = 'otros "
    "alimentos y bebidas'. The mass proves it: code 9 holds ~80% of observations "
    "in 2013-2017 (desayuno 7%, almuerzo 13%), which no dinner share can explain, "
    "and once Cena gets its own code in 2019+ it is only ~8% while code 9 stays "
    "37-45%. Code 9 is the catch-all 'Otros' in every year."
)

FIX = {
    ("p5291c", "0"): ("Sabe", E_SABE),
    ("p530b", "0"): ("Tiene ganancia", E_GAN),
}


def main() -> int:
    o = pd.read_csv(OUT, encoding="utf-8-sig", dtype=str)
    total = 0
    for (col, code), (label, ev) in FIX.items():
        hit = (o.column == col) & (o.code == code)
        was = o.loc[hit, "label"].value_counts().to_dict()
        n = int((hit & (o.label != label)).sum())
        o.loc[hit, "label"] = label
        o.loc[hit, "evidence"] = ev
        total += n
        print(f"  {col} code {code}: {was} -> {label!r}  ({n} rows)")

    r559 = o.column.str.match(r"r559_\d+$", na=False) & (o.code == "9")
    was = o.loc[r559, "label"].value_counts().to_dict()
    n = int((r559 & (o.label != "Otros")).sum())
    o.loc[r559, "label"] = "Otros"
    o.loc[r559, "evidence"] = E_OTROS
    total += n
    print(f"  r559_* code 9: {was} -> 'Otros'  ({n} rows, "
          f"{o.loc[r559, 'column'].nunique()} columns)")

    o.to_csv(OUT, index=False, encoding="utf-8")

    chk = pd.read_csv(OUT, encoding="utf-8-sig", dtype=str)
    for (col, code), (label, _) in FIX.items():
        got = set(chk[(chk.column == col) & (chk.code == code)].label.dropna())
        assert got <= {label}, f"{col} code {code} still {got}"
    r = chk.column.str.match(r"r559_\d+$", na=False) & (chk.code == "9")
    got = set(chk.loc[r, "label"].dropna())
    assert got <= {"Otros"}, f"r559 code 9 still {got}"
    assert "Cena" not in got, "r559 code 9 is still labelled Cena"
    print(f"\ncorrected {total} rows; each column's code now has ONE meaning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
