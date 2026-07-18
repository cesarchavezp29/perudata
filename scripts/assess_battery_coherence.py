"""Which 'No marcado' battery flips are real, and which pooled distinct questions?

The battery sweep grouped columns by a stem stripped of one index level. For
proper split batteries (p558h1_01.. '¿cómo pagó por X?') that is right. But a
coarse stem pools DISTINCT questions: 'p51' swept p510, p511, p513... which are
different employment items, and the admin0 co-occurrence test passed spuriously
because any two unrelated flags have rows where one is 1 and another 0. INEI
even labels p513 code 0 'Pase (no es omisión)' -- an explicit pase, not a
'No marcado'.

The reliable discriminator is INEI's QUESTION TEXT (the variable label). Real
battery siblings share it up to the option name ('... a través de una/un:
Computadora' / ': Laptop'); pooled distinct questions do not. For each flipped
stem this prints the member columns and the longest common prefix of their
question texts, and flags a family as INCOHERENT when that shared prefix is
short -- those are the spurious flips to revert.
"""
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import pandas as pd  # noqa: E402

from perudata import dictionary as dic  # noqa: E402

XW = Path(__file__).parents[1] / "src" / "perudata" / "crosswalks" / \
    "enaho_label_overrides.csv"
# modules whose batteries were flipped by the cross-module sweep (a86c699)
SWEPT = ["01", "03", "04", "05", "84"]


def stem_of(col: str) -> str:
    return re.sub(r"(_\d+|\d)$", "", col)


def qtext(col: str, mod: str) -> str:
    """INEI's question text for a column, any year (lower, first found)."""
    v = dic.variable(col)
    v = v[v["module"] == str(mod).zfill(2)]
    for lab in v["label"]:
        if isinstance(lab, str) and lab.strip():
            return lab.strip().lower()
    return ""


def common_prefix(strings: list) -> int:
    if not strings:
        return 0
    s1, s2 = min(strings), max(strings)
    i = 0
    while i < len(s1) and i < len(s2) and s1[i] == s2[i]:
        i += 1
    return i


def main() -> int:
    o = pd.read_csv(XW, encoding="utf-8-sig", dtype=str)
    # columns the sweep set to 'No marcado' at code 0, in the swept modules
    flipped = o[(o.module.isin(SWEPT)) & (o.code == "0")
                & (o.label == "No marcado")
                & (o.evidence.str.contains("MULTIPLE-RESPONSE FLAG, proven "
                                           "administered", na=False))]
    fams = defaultdict(lambda: defaultdict(set))
    for r in flipped.itertuples(index=False):
        fams[r.module][stem_of(r.column)].add(r.column)

    coherent, incoherent = [], []
    for mod in sorted(fams):
        for stem, cols in sorted(fams[mod].items()):
            texts = [qtext(c, mod) for c in sorted(cols)]
            texts = [t for t in texts if t]
            cp = common_prefix(texts) if len(texts) >= 2 else 0
            rec = (mod, stem, sorted(cols), cp, texts[:2])
            # a real battery shares a long question stem; >=20 chars is a
            # conservative bar (question stems are long: 'en el mes anterior...')
            (coherent if cp >= 20 else incoherent).append(rec)

    print("=== COHERENT batteries (shared question text >= 20 chars) ===")
    for mod, stem, cols, cp, ex in coherent:
        print(f"  {mod} {stem}* ({len(cols)} cols) cp={cp}: {ex[0][:50]!r}")
    print(f"\n=== INCOHERENT -- pooled distinct questions (REVERT) ===")
    n_rev = 0
    for mod, stem, cols, cp, ex in incoherent:
        print(f"  {mod} {stem}* ({len(cols)} cols) cp={cp}: {cols[:5]}")
        for c, t in zip(sorted(cols)[:3], ex):
            print(f"        {c}: {t[:60]!r}")
        n_rev += len(cols)
    print(f"\ncoherent families: {len(coherent)} | incoherent: {len(incoherent)} "
          f"({n_rev} columns to revert)")
    # write the incoherent column list for the revert step
    rev = [(m, c) for m, s, cols, cp, ex in incoherent for c in cols]
    pd.DataFrame(rev, columns=["module", "column"]).to_csv(
        Path(__file__).parent / "spurious_battery_cols.csv", index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
