"""One code, one spelling. Merge the labels that differ only as TYPOGRAPHY.

WHY THIS IS NOT COSMETIC. Pool years and group by label, and 'Rio, acequia,
lago, laguna' and 'Río, acequia, lago, laguna' are TWO categories. The category
splits, each half looks like it appears and vanishes mid-panel, and nothing in
the data changed -- only how INEI typed it that year. p110 code 4 ships SIX
spellings of one water source:

    'Camion-cisterna u otro similar'
    'Camión – cisterna u otro similar'
    'Camión-cisterna u otro similar'
    'Camión– cisterna u otro similar'
    'Camión–cisterna u otro similar'
    '¿ Camión – cisterna u otro similar?'

WHAT IS IN SCOPE -- AND WHAT IS DELIBERATELY NOT. Only groups whose labels are
IDENTICAL after stripping accents, case and punctuation. That is a provably
meaning-preserving test: if two strings collapse to the same letters and digits,
they name the same category.

The 355 groups that do NOT collapse are left alone, because that class contains
GENUINE RECODES that merely look like abbreviations:

    p102 code 3: 'Adobe o tapia' -> 'Adobe'
    p102 code 4: 'Quincha'       -> 'Tapia'

INEI really did split "Adobe o tapia" into separate codes and shift the rest
down. A prefix or fuzzy match would silently merge a genuine recode into one
label and erase a real break in the series -- the exact damage this script
exists to undo. So: no fuzzy matching, no prefix rules, no abbreviation
dictionary. Exact-collapse only.

CHOOSING THE SURVIVOR, in order:
  1. Drop interrogative forms ('¿Otra?'). Those are the question text leaking
     into a value label -- an artifact of parsing, never INEI's category name.
     Kept only if every variant is interrogative.
  2. Prefer the most correctly typed Spanish: the most accented characters.
     'Sí' over 'Si', 'Río' over 'Rio', 'Camión' over 'Camion'.
  3. Prefer the form with real word spacing: 'Lima Metropolitana' over
     'LimaMetropolitana' (longer, once accents are equal).
  4. Break remaining ties by frequency, then alphabetically, so the result is
     deterministic and a rerun is a no-op.
"""
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parents[1]
OUT = ROOT / "src" / "perudata" / "crosswalks" / "enaho_label_overrides.csv"

KEY = ["module", "column", "code"]


def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c))


def collapse(s: str) -> str:
    """Letters and digits only, unaccented, lowercased."""
    return re.sub(r"[^a-z0-9]", "", strip_accents(s).lower())


def n_accents(s: str) -> int:
    return sum(1 for c in unicodedata.normalize("NFKD", str(s))
               if unicodedata.combining(c))


def is_question(s: str) -> bool:
    t = str(s).strip()
    return t.startswith("¿") or t.endswith("?")


def pick(labels: list[str], freq: dict) -> str:
    pool = [x for x in labels if not is_question(x)] or list(labels)
    return sorted(
        pool,
        key=lambda x: (-n_accents(x), -len(x), -freq.get(x, 0), x),
    )[0]


def main(apply: bool) -> int:
    o = pd.read_csv(OUT, encoding="utf-8-sig", dtype=str)
    groups = o.groupby(KEY).label.apply(lambda s: sorted(set(s.dropna())))
    multi = groups[groups.apply(len) > 1]

    plan, skipped = {}, 0
    for k, labels in multi.items():
        if len({collapse(x) for x in labels}) != 1:
            skipped += 1          # genuinely different -> a recode, leave it
            continue
        sub = o[(o.module == k[0]) & (o.column == k[1]) & (o.code == k[2])]
        freq = sub.label.value_counts().to_dict()
        plan[k] = pick(labels, freq)

    print(f"groups with >1 label            : {len(multi):,}")
    print(f"  collapse-identical (in scope) : {len(plan):,}")
    print(f"  genuinely different (SKIPPED) : {skipped:,}")

    rows = 0
    for k, want in plan.items():
        m = (o.module == k[0]) & (o.column == k[1]) & (o.code == k[2])
        rows += int((m & (o.label != want)).sum())
    print(f"\nrows that would change          : {rows:,}")

    print("\nsample of the merges:")
    for k, want in list(plan.items())[:10]:
        others = [x for x in multi[k] if x != want]
        print(f"  {k[0]} {k[1]:<10} code {k[2]:<3} KEEP {want!r}")
        for x in others[:4]:
            print(f"       drop {x!r}")

    if not apply:
        print("\n(dry run -- pass --apply to write)")
        return 0

    for k, want in plan.items():
        m = (o.module == k[0]) & (o.column == k[1]) & (o.code == k[2])
        o.loc[m, "label"] = want
    o.to_csv(OUT, index=False, encoding="utf-8")

    chk = pd.read_csv(OUT, encoding="utf-8-sig", dtype=str)
    g2 = chk.groupby(KEY).label.nunique()
    for k in plan:
        assert g2.loc[k] == 1, f"{k} still has {g2.loc[k]} labels"
    # the skipped groups must be untouched
    g3 = chk.groupby(KEY).label.apply(lambda s: sorted(set(s.dropna())))
    still = sum(1 for k, labs in g3.items()
                if len(labs) > 1 and len({collapse(x) for x in labs}) != 1)
    assert still == skipped, f"recode groups changed: {still} != {skipped}"
    assert not chk.label.astype(str).str.contains("�").any(), "mojibake"
    print(f"\napplied: {rows:,} rows now carry one spelling per code")
    print(f"left alone: {skipped:,} genuine-recode groups, untouched")
    return 0


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
