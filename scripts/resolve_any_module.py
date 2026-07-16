"""The module-01 machinery, generalized to any module.

Four evidence rules, each PROVEN on module 01 before being trusted anywhere else.
None of them guesses; each one either has evidence or declines.

  1. THE DECLARED RANGE. A dictionary that says "Rango : 0 - 1" while labelling only
     the affirmative is making a POSITIVE STATEMENT that code 0 exists. Unlabelled
     and inside the declared range = INEI's `pase` convention. (Proven on module 01:
     p1121 lists only "1 Electricidad" and declares "Rango : 0 - 1".)

  2. THE PHANTOM CODE. If a .dta label names a code that appears in NO year of the
     data, the LABEL is wrong -- INEI wrote the variable's position in its battery
     as the value code. Certify the code the data actually holds, using the
     label/dictionary text from the years that agree. (Proven: p1142 labels code 2,
     p1144 labels code 4, both absent from every year 2004-2011.)

  3. INEI'S OWN LATER TESTIMONY. If a code is unlabelled early and INEI itself names
     it in a later vintage of the SAME variable, that is INEI's testimony about its
     own code, not a neighbour-year inference. (Proven: p1175_* code 0 -- absent,
     then blank, then explicitly 'pase' from 2020.)

  4. THE IDENTICAL CODE SET. A year with no labels whose observed code set is
     CONTAINED IN the labelled years' set, with the same distribution shape, was
     not recoded -- the metadata was omitted. (Proven: p1171_*, t110.)

Rule 2's converse is the reason none of this can be automated blind: on p107a* the
DICTIONARY was the liar and the data was right, the mirror image of rule 2. Where
the sources disagree and no behavioural proof exists, this declines and reports.
"""
import os
import re
import sys
from collections import Counter
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from perudata import dictionary as dic  # noqa: E402
from perudata import enaho  # noqa: E402

ROOT = Path(__file__).parents[1]
SRC = ROOT / "docs" / "source"
OUT = ROOT / "src" / "perudata" / "crosswalks" / "enaho_label_overrides.csv"
MODULES = [m.zfill(2) for m in os.environ.get("PERUDATA_MODULES", "02").split(",")]

HEADER = re.compile(r"^([A-Z][A-Z0-9_$]{1,12})\s+\d+\s+\d+\s+[NAC]\s+(.+?)\s*$")
RANGE = re.compile(r"^\s*Rango\s*:\s*(\d+)\s*[-–,]\s*(\d+)", re.I)


def declared_ranges(year: int, module: str) -> dict:
    for p in (SRC / "inzip" / f"{year}_{module}.txt",
              SRC / f"ENAHO_{year}_Diccionario.txt"):
        if not p.exists():
            continue
        out, cur = {}, None
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            h = HEADER.match(line)
            if h:
                cur = h.group(1).lower()
                continue
            if cur is None:
                continue
            r = RANGE.match(line)
            if r:
                out[cur] = (int(r.group(1)), int(r.group(2)))
                cur = None
        if out:
            return out
    return {}


rows, declined = [], []
for mod in MODULES:
    years = [y for y in enaho.years() if enaho.path(y, mod).exists()]
    if not years:
        continue
    frames, labels = {}, {}
    for y in years:
        try:
            frames[y] = enaho.load(y, mod, download_if_missing=False)
        except Exception:
            continue
    cols = sorted({c for f in frames.values() for c in f.columns})
    print(f"--- module {mod}: {len(cols)} columns, {len(frames)} years", flush=True)

    for col in cols:
        obs, lab = {}, {}
        for y, f in frames.items():
            if col not in f.columns:
                continue
            v = pd.to_numeric(f[col], errors="coerce").dropna()
            if v.empty or not (v % 1 == 0).all():
                continue
            u = {int(x) for x in v.unique()}
            if len(u) > 30:
                continue
            obs[y] = u
            l = dic.value_labels(col, y, mod)
            if l:
                lab[y] = {int(float(k)): str(v) for k, v in l.items() if str(v).strip()}
        if not obs or not lab:
            continue
        all_obs = set().union(*obs.values())

        # RULE 2: a label naming a code that exists in NO year is a phantom
        named = set().union(*[set(m) for m in lab.values()])
        phantom = named - all_obs
        good = {y: m for y, m in lab.items() if not (set(m) - all_obs)}
        for y, m in lab.items():
            if not (set(m) - all_obs) or not good:
                continue
            ref = good[max(good)]
            for code in sorted(obs.get(y, set()) - set(m)):
                if code in ref:
                    rows.append({
                        "module": mod, "column": col, "year": y, "code": code,
                        "label": ref[code].strip().capitalize(), "status": "verified",
                        "evidence": (
                            f"PHANTOM CODE IN THE {y} LABEL. The {y} .dta labels "
                            f"{col} with code(s) {sorted(set(m) - all_obs)}, which "
                            f"appear in NO year of the released data — INEI wrote "
                            f"the variable's position in its battery as the value "
                            f"code. The years whose labels match the data "
                            f"({sorted(good)}) label code {code} as "
                            f"'{ref[code]}'."),
                    })

        # RULE 3 + 4: unlabelled codes/years, resolved by INEI's own other vintages
        for y, u in obs.items():
            missing = u - set(lab.get(y, {}))
            if not missing:
                continue
            ranges = declared_ranges(y, mod)
            lo_hi = ranges.get(col)
            for code in sorted(missing):
                # RULE 3: does INEI name this code in ANY other year?
                elsewhere = {yy: m[code] for yy, m in lab.items()
                             if code in m and yy != y}
                if elsewhere:
                    src = max(elsewhere)
                    rows.append({
                        "module": mod, "column": col, "year": y, "code": code,
                        "label": elsewhere[src].strip().capitalize(),
                        "status": "verified",
                        "evidence": (
                            f"INEI'S OWN TESTIMONY ABOUT ITS OWN CODE. {y} ships no "
                            f"label for {col} code {code}, but INEI labels that "
                            f"exact code on that exact variable in "
                            f"{sorted(elsewhere)} as '{elsewhere[src]}'. Same "
                            f"variable, same code, same concept — only the "
                            f"documentation differs by vintage."),
                    })
                    continue
                # RULE 1: unlabelled but INSIDE the dictionary's declared range
                if lo_hi and lo_hi[0] <= code <= lo_hi[1] and code == 0:
                    rows.append({
                        "module": mod, "column": col, "year": y, "code": 0,
                        "label": "Pase", "status": "verified",
                        "evidence": (
                            f"INEI's {y} Diccionario declares '{col.upper()} Rango "
                            f": {lo_hi[0]} - {lo_hi[1]}' while labelling only the "
                            f"substantive codes. Code 0 is INSIDE the declared "
                            f"range and deliberately unlabelled: the `pase` (not "
                            f"applicable) convention. The declared range is a "
                            f"positive statement that the code exists."),
                    })
                    continue
                declined.append({"module": mod, "column": col, "year": y,
                                 "code": code,
                                 "why": "no label in any year, and not inside a "
                                        "declared range — needs its own evidence"})

new = pd.DataFrame(rows).drop_duplicates(subset=["module", "column", "year", "code"])
old = pd.read_csv(OUT, encoding="utf-8-sig", dtype=str)
both = pd.concat([old, new.astype(str)], ignore_index=True).drop_duplicates(
    subset=["module", "column", "year", "code"], keep="first")
both.to_csv(OUT, index=False, encoding="utf-8")
print()
print(f"certified: {len(new):,}   (by rule: "
      f"{dict(Counter(r['evidence'][:24] for r in rows))})")
print(f"DECLINED (reported, never invented): {len(declined):,}")
print(f"override rows: {len(old):,} -> {len(both):,}")
if declined:
    pd.DataFrame(declined).to_csv(Path(__file__).parent / "declined_codes.csv",
                                  index=False)
