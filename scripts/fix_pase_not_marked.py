"""Code 0 on a multiple-response flag is "No marcado", never "Pase".

THE BUG. The crosswalk shipped the SAME code, in the SAME column, meaning two
different things depending on the year:

    p3152 code 0 -> "Pase"       for 2007-2020
    p3152 code 0 -> "No marcado" for 2021-2025

That is the precise defect harmonizing exists to remove, and it was invisible
because the resolver was append-only: it wrote
    concat([old, new]).drop_duplicates(keep="first")
so a row written by an EARLIER, WEAKER rule permanently outranked the rule that
supersedes it. Rule 1 (code is inside the dictionary's declared range, so it is
`pase`) had already claimed code 0 for every year with a published dictionary.
Rule 5 (multiple-response flag, proven by structure) could only reach 2021-2025,
where no dictionary exists to declare a range.

WHICH IS RIGHT, AND WHY. `Pase` means the question was never put to this person.
These columns are 6-slot multiple-response batteries, and the data refutes `pase`
outright -- in every year and every battery:

    rows outside the universe : ALL SIX columns are NA (never 0)
    rows inside the universe  : marking NONE of the six = 0, without exception

Not one in-universe row marks nothing. So a 0 cell always sits in a row that DID
answer -- it marked a different slot (p3151 "comprado" takes ~97% of p315x). The
person was asked and said no. That is "No marcado". And rows marking 2+ slots
(p314a*: 49/54/68 in 2004/2005/2006) prove these are genuine multiple-response
sets rather than a categorical being misread.

VERIFIED BEFORE WRITING: 23 columns x the years below, markNONE == 0 everywhere.

SCOPE. Only (code 0, "Pase" -> "No marcado") on the verified columns. The other
disagreements in override_disagreements.csv are left ALONE: the cosmetic ones
(accents, abbreviations) are harmless and the old label is stable, and the
substantive ones ('Con imputacion hot-deck' -> 'Cuestionario en hojas') have no
evidence yet and must not be flipped on a rule's say-so.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parents[1]
OUT = ROOT / "src" / "perudata" / "crosswalks" / "enaho_label_overrides.csv"
DIS = ROOT / "scripts" / "override_disagreements.csv"

EVIDENCE = (
    "MULTIPLE-RESPONSE FLAG, proven by structure and by the battery's own data. "
    "{col} is one slot of a 6-slot battery. Rows outside the universe hold NA in "
    "all six slots, and among rows inside it, ZERO mark none of the six -- so a "
    "code-0 cell always belongs to a row that answered by marking a different "
    "slot. The person was asked and said no, which is 'No marcado', not 'Pase' "
    "(never asked). Supersedes the earlier 'Pase' row, which came from the weaker "
    "inference that code 0 sits inside the dictionary's declared range; the "
    "declared range proves the code EXISTS, not that it means 'not applicable'."
)

VERIFIED = [f"p3121a{i}" for i in range(1, 7)] + \
           [f"p3122a{i}" for i in range(1, 7)] + \
           [f"p314a{i}" for i in range(1, 7)] + \
           [f"p315{i}" for i in range(2, 7)]


def main() -> int:
    o = pd.read_csv(OUT, encoding="utf-8-sig", dtype=str)
    hit = (
        (o.code == "0")
        & (o.label == "Pase")
        & (o.column.isin(VERIFIED))
    )
    n = int(hit.sum())
    if not n:
        print("nothing to fix (already applied?)")
        return 0

    # refuse to touch anything the disagreement report did not independently flag
    dis = pd.read_csv(DIS, encoding="utf-8-sig", dtype=str)
    flagged = set(
        zip(*[dis[dis.label_new == "No marcado"][c]
              for c in ("column", "year", "code")])
    )
    keys = set(zip(*[o.loc[hit, c] for c in ("column", "year", "code")]))
    unbacked = keys - flagged
    if unbacked:
        print(f"REFUSING: {len(unbacked)} rows not independently flagged by the "
              f"rules, e.g. {sorted(unbacked)[:3]}")
        return 1

    before = o.loc[hit, "label"].value_counts().to_dict()
    o.loc[hit, "label"] = "No marcado"
    o.loc[hit, "evidence"] = [EVIDENCE.format(col=c) for c in o.loc[hit, "column"]]
    o.to_csv(OUT, index=False, encoding="utf-8")

    print(f"corrected {n} rows: {before} -> 'No marcado'")
    print(f"  columns: {sorted(o.loc[hit, 'column'].unique())}")
    print(f"  years  : {sorted(o.loc[hit, 'year'].unique())}")

    chk = pd.read_csv(OUT, encoding="utf-8-sig", dtype=str)
    still = chk[(chk.code == "0") & (chk.label == "Pase")
                & (chk.column.isin(VERIFIED))]
    assert still.empty, f"{len(still)} rows survived the fix"

    # the point of the exercise: one code, one meaning, every year
    for col in VERIFIED:
        lab = chk[(chk.column == col) & (chk.code == "0")].label.unique()
        assert len(lab) <= 1, f"{col} code 0 STILL means {list(lab)} across years"
    print("verified: every fixed column's code 0 now has ONE meaning in all years")
    return 0


if __name__ == "__main__":
    sys.exit(main())
