"""p314b1_8 / p314b1_9: the internet-device battery, mislabelled in BOTH sources.

THE DAMAGE. Pool 2019-2025 through the public API and the shipped crosswalk makes
"Celular sin plan de datos" vanish at 2023 while "Otro" spikes -- a trend break
manufactured entirely by the label, with the data untouched:

    p314b1_8 code 8 : 'Celular sin plan de datos' (2019-2022) -> 'Otro' (2023-2025)
    p314b1_9 code 9 : 'Otro' (2019-2022) -> 'Celular con plan de datos' (2023-2025)
    p314b1_9 code 0 : 'Celular con plan de datos' (2021-2022) -> 'Pase' (2023-2025)

WHY BOTH HALVES ARE WRONG. INEI made a DIFFERENT error in each of its two sources,
so neither can be trusted wholesale and no source ranking can fix this:

  * the .dta value label is SHIFTED for _9:
        p314b1_9 -> {0: 'celular con plan de datos', 9: 'otro'}
    while all five siblings are {0: 'pase', N: <substantive>}. The substantive
    label slid onto code 0, and code 9 inherited _7's 'otro'.
  * the DICTIONARY's value-label line is a copy-paste typo for _8:
        P314B1_8 ...: Celular sin plan de datos    <- variable label
        0. Pase
        8. Otro                                    <- copied from _7
    while _8's own question text says "Celular sin plan de datos".

Ranking the dictionary over the .dta would fix _9 and BREAK _8. Ranking the .dta
over the dictionary would do the reverse.

THE ARBITER: THE VARIABLE LABEL. For a flag battery -- a column X_N holding only
{0, N}, which the dictionary itself declares as "Rango 0-N" -- the question text
after the colon IS what code N means. Tested against every in-zip dictionary in
docs/source/inzip, restricted to true flag batteries by that declared range:

    variable-label suffix AGREES with the value label : 136
    mismatches                                        :  30
        P307A4_6  var='Correo'           val='Correo electronico'   (truncation)
        P307A4_7  var='Llamada'          val='Llamada telefonica'   (truncation)
        P314B1_8  var='Celular sin plan' val='Otro'   <- the ONLY real error, x22

So across the whole package exactly one INEI dictionary value-label is genuinely
wrong, and it is this one. The truth, agreed by the question text in 22 vintages
AND by INEI's own .dta value label for _8:

    _7 = Otro
    _8 = Celular sin plan de datos
    _9 = Celular con plan de datos

and code 0 = Pase for every slot, as the dictionary states and five of six
siblings already carry.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parents[1]
OUT = ROOT / "src" / "perudata" / "crosswalks" / "enaho_label_overrides.csv"

E8 = (
    "CORRECTS A COPY-PASTE TYPO IN INEI'S DICTIONARY. The dictionary labels "
    "P314B1_8 code 8 as 'Otro', but that is _7's label copied one slot down: "
    "P314B1_8's own question text reads 'El servicio de Internet lo uso a traves "
    "de una/un: Celular sin plan de datos', and INEI's .dta value label for this "
    "exact column and code independently says 'celular sin plan de datos'. For a "
    "flag battery (a column X_N holding only {0,N}, which the dictionary declares "
    "as 'Rango 0-8'), the question text after the colon IS what code N means -- "
    "verified on 136 flag batteries across every in-zip dictionary, where P314B1_8 "
    "is the ONE genuine mismatch (the other 2 are truncations of the same phrase)."
)
E9 = (
    "CORRECTS A SHIFTED .dta VALUE LABEL. INEI's .dta labels p314b1_9 as "
    "{0: 'celular con plan de datos', 9: 'otro'} while all five siblings are "
    "{0: 'pase', N: <substantive>} -- the substantive label slid onto code 0 and "
    "code 9 inherited _7's 'otro'. The dictionary is right here: its question text "
    "AND its value-label line both say code 9 is 'Celular con plan de datos', and "
    "it lists '0. Pase' exactly as every sibling does. The earlier row came from "
    "carrying the broken .dta label back to years that ship no label of their own."
)
E0 = (
    "PASE, per the dictionary and every sibling. The dictionary lists '0. Pase' "
    "for p314b1_9, and p314b1_1/_2/_6/_7/_8 all carry 'Pase' at code 0. The "
    "earlier 'Celular con plan de datos' was INEI's shifted .dta label -- the "
    "substantive label belongs at code 9, not code 0 -- carried into 2021-2022 "
    "from a vintage whose label was already wrong."
)

TRUTH = {
    ("p314b1_8", "8"): ("Celular sin plan de datos", E8),
    ("p314b1_9", "9"): ("Celular con plan de datos", E9),
    ("p314b1_9", "0"): ("Pase", E0),
}


def main() -> int:
    o = pd.read_csv(OUT, encoding="utf-8-sig", dtype=str)
    changed = 0
    for (col, code), (label, ev) in TRUTH.items():
        hit = (o.column == col) & (o.code == code)
        if not hit.any():
            print(f"  {col} code {code}: no rows"); continue
        was = o.loc[hit, "label"].value_counts().to_dict()
        wrong = hit & (o.label != label)
        n = int(wrong.sum())
        o.loc[hit, "label"] = label
        o.loc[hit, "evidence"] = ev
        changed += n
        print(f"  {col} code {code}: {was} -> {label!r}  ({n} rows corrected)")
    o.to_csv(OUT, index=False, encoding="utf-8")

    chk = pd.read_csv(OUT, encoding="utf-8-sig", dtype=str)
    for (col, code), (label, _) in TRUTH.items():
        got = chk[(chk.column == col) & (chk.code == code)].label.unique()
        assert set(got) <= {label}, f"{col} code {code} still {list(got)}"
    # the whole point: no year-to-year label break inside the battery
    for col in ("p314b1_7", "p314b1_8", "p314b1_9"):
        for code in chk[chk.column == col].code.unique():
            labs = chk[(chk.column == col) & (chk.code == code)].label.unique()
            assert len(labs) == 1, f"{col} code {code} means {list(labs)} by year"
    print(f"\ncorrected {changed} rows")
    print("verified: p314b1_7/_8/_9 each have ONE meaning per code across all years")
    return 0


if __name__ == "__main__":
    sys.exit(main())
