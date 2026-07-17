"""Repair cross-module collisions in the numeric modules against INEI's .dta.

THE BUG. Modules 07-28/77/78 have no per-module in-zip dictionary, so the
resolver drew dictionary evidence from the STANDALONE whole-survey dictionary,
which is not module-scoped. Column names collide across modules -- p606n is
personal-care products in module 78 but esparcimiento in module 12 -- so a
colliding name pulled the WRONG module's labels. INEI's .dta embedded labels are
module-scoped and correct, so the .dta is ground truth here.

THE DISCRIMINATOR. For each new-module row whose resolved label differs from the
module's own .dta label for that exact (column, code), measure token overlap
(Jaccard on the alphanumeric word sets):

  * LOW overlap  -> a different concept: a collision (p606n esparcimiento on a
    personal-care variable) or parse garbage ('Vaso  preparadobenéficas)').
    Adopt the .dta label -- module-scoped truth.
  * HIGH overlap -> the same concept, different typography ('bodega (x menor)'
    vs 'bodega (por menor)'). Keep the resolver's label; it is the properly
    cased/accented form, and the .dta is lowercase and occasionally typo'd
    ('autosuministo', 'aarea').

Only rows the .dta can adjudicate are touched. Dictionary-only codes (no .dta
label) are left as resolved -- the .dta cannot speak to them. Everything is
previewed; --apply writes, then re-checks that no adopted row still disagrees.
"""
import os
import re
import sys
import unicodedata
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")
sys.path.insert(0, "src")

import pandas as pd  # noqa: E402
import pyreadstat  # noqa: E402

from perudata import enaho  # noqa: E402

ROOT = Path(__file__).parents[1]
XW = ROOT / "src" / "perudata" / "crosswalks" / "enaho_label_overrides.csv"
NEW = ["07", "08", "09", "10", "11", "12", "13", "15", "16", "17", "18",
       "22", "23", "24", "25", "26", "27", "28", "77", "78"]
THRESH = 0.5   # Jaccard below this = different concept -> adopt .dta


def toks(s: str) -> set:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return {w for w in re.findall(r"[a-z0-9]+", s) if len(w) > 1}


def jaccard(a: str, b: str) -> float:
    ta, tb = toks(a), toks(b)
    if not ta and not tb:
        return 1.0
    return len(ta & tb) / max(1, len(ta | tb))


def _collapse(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())


def edit_distance(a: str, b: str) -> int:
    a, b = _collapse(a), _collapse(b)
    if abs(len(a) - len(b)) > 3:
        return 99
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def is_typo(a: str, b: str) -> bool:
    """Same word, one misspelled: keep the correctly-spelled resolver form
    rather than adopt INEI's .dta typo ('Autosuministro' vs 'autosuministo')."""
    return 0 < edit_distance(a, b) <= 2


def titlecase(s: str) -> str:
    s = re.sub(r"\s+", " ", str(s).strip())
    s = re.sub(r"\s*\(\s*", " (", s)
    s = re.sub(r"\s*\)", ")", s)
    return s[:1].upper() + s[1:] if s else s


def dta_labels(mod: str, y: int) -> dict:
    p = enaho.path(y, mod)
    if not p.exists():
        return {}
    try:
        _, meta = pyreadstat.read_dta(str(p), metadataonly=True)
    except Exception:
        return {}
    return {c.lower(): {(str(int(k)) if float(k).is_integer() else str(k)): v
                        for k, v in d.items()}
            for c, d in meta.variable_value_labels.items()}


def main(apply: bool) -> int:
    o = pd.read_csv(XW, encoding="utf-8-sig", dtype=str)
    cache = {}
    adopt, keep = [], 0
    for mod in NEW:
        sub = o[o.module == mod]
        for y in sub.year.unique():
            cache.setdefault((mod, y), dta_labels(mod, int(y)))
        for idx, r in sub.iterrows():
            d = cache[(mod, r.year)].get(r.column, {})
            if r.code not in d or r.label == "No marcado":
                continue
            if toks(r.label) == toks(d[r.code]):
                continue                       # same words -> nothing to do
            if is_typo(r.label, d[r.code]):
                keep += 1                      # .dta typo -> keep clean resolver
                continue
            if jaccard(r.label, d[r.code]) < THRESH:
                adopt.append((idx, mod, r.column, r.year, r.code,
                              r.label, titlecase(d[r.code])))
            else:
                keep += 1

    print(f"rows the .dta can adjudicate and that genuinely differ:")
    print(f"  KEEP resolver (same concept, better typography): {keep}")
    print(f"  ADOPT .dta (different concept -> collision/garbage): {len(adopt)}")
    a = pd.DataFrame(adopt, columns=["idx", "module", "column", "year", "code",
                                     "was", "now"])
    a.to_csv(ROOT / "scripts" / "collision_repairs.csv", index=False,
             encoding="utf-8")
    print("\n  adopting (was -> now), unique by column/code:")
    for r in a.drop_duplicates(["module", "column", "code"]).head(40).itertuples(index=False):
        print(f"   {r.module} {r.column:<9} c{r.code}: {r.was[:36]!r} -> {r.now[:36]!r}")

    if not apply:
        print("\n(dry run -- pass --apply to write)")
        return 0

    for idx, mod, col, yr, code, was, now in adopt:
        o.at[idx, "label"] = now
        o.at[idx, "evidence"] = (
            f"MODULE-SCOPED .dta OVERRIDES A CROSS-MODULE DICTIONARY COLLISION. "
            f"The resolver drew this label from the standalone whole-survey "
            f"dictionary, where the column name {col} collides with a different "
            f"module's variable, giving {was!r} -- a different concept (token "
            f"overlap < {THRESH}). INEI's own module-{mod} .dta labels this code "
            f"{now!r}, which is module-scoped ground truth.")
    o.to_csv(XW, index=False, encoding="utf-8")

    chk = pd.read_csv(XW, encoding="utf-8-sig", dtype=str)
    for idx, mod, col, yr, code, was, now in adopt:
        assert chk.at[idx, "label"] == now
    print(f"\napplied {len(adopt)} collision repairs from module-scoped .dta")
    return 0


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
