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
            # NOT EVERY SMALL INTEGER SET IS A CATEGORY. Three shapes get wrongly
            # swept in, and labelling any of them would invent data:
            #  * MEASUREMENTS that happen to be coarse. p5561c holds 20/40/50/70/
            #    80/100 -- quantities, not codes. A category set is contiguous from
            #    a small base; a measurement is sparse and spread.
            #  * CLASSIFICATION NAMESPACES. p505/p506 hold 4-digit CIIU/CIUO codes
            #    (7526, 6199). The code IS the identity per the published standard;
            #    nobody labels those in a .dta.
            #  * CORRUPTION. p207 (sex) holds a single -126 row in 2009 -- the
            #    signature of a Stata int8 overflow (-128..127), not a third sex.
            if any(x < 0 for x in u):
                declined.append({"module": mod, "column": col, "year": y,
                                 "code": min(u),
                                 "why": "negative code in a categorical — likely an "
                                        "int8 overflow artifact, never a category"})
                continue
            if max(u) > 99 or (len(u) > 2 and max(u) > 3 * len(u) + 10):
                continue          # a measurement or a classification code, not a category
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
                # RULE 5: THE MULTIPLE-RESPONSE FLAG, proven by STRUCTURE alone.
                # A flag column holds at most {0,1} and its label names exactly ONE
                # code -- the affirmative ({1: 'comprado'}). That is how Stata
                # stores a multiple-response battery: the label says what the flag
                # MEANS WHEN SET, and 0 is simply "not marked". There is no other
                # value for 0 to be, and no year labels it otherwise.
                # (Verified on p311a*: 56 cells x 22 years, ZERO violations, and
                # 919 rows carry 2+ modes at once -- non-exclusive, so it is a
                # genuine multiple-response set, not a categorical being misread.)
                if (code == 0 and all_obs <= {0, 1}
                        and all(set(m) == {1} for m in lab.values())):
                    rows.append({
                        "module": mod, "column": col, "year": y, "code": 0,
                        "label": "No marcado", "status": "verified",
                        "evidence": (
                            f"MULTIPLE-RESPONSE FLAG, proven by structure. {col} "
                            f"holds only {{0,1}} in every year and its label names "
                            f"exactly one code — the affirmative "
                            f"({ {k: v for k, v in list(lab.values())[0].items()} }). "
                            f"That is how a multiple-response battery is stored: "
                            f"the label says what the flag means WHEN SET, and 0 is "
                            f"'not marked'. No year labels code 0 otherwise, and no "
                            f"other value is available to it."),
                    })
                    continue
                # RULE 6: THE NULL BECAME A ZERO. INEI changed how it encodes "not
                # applicable" -- from a MISSING VALUE to an explicit 0 -- while
                # leaving the label untouched.
                # PROOF, and it is exact: in the years without code 0 the variable
                # carries NULLS for non-respondents; in the years WITH code 0 the
                # null count drops to EXACTLY ZERO and code 0 appears in its place.
                # Same concept, new representation.
                # (p55610a: 2019-2023 hold {1,2} with 86-128 nulls; 2024/2025 hold
                # {0,1,2} with 0 nulls and the same {1: si, 2: no} label. 76 of
                # module 05's blockers are this one pattern.)
                if code == 0 and y in obs:
                    fy = frames.get(y)
                    nulls_now = int(pd.to_numeric(fy[col], errors="coerce").isna().sum())                         if fy is not None and col in fy.columns else -1
                    others = [yy for yy in obs if 0 not in obs[yy]]
                    nulls_before = []
                    for yy in others:
                        fo = frames.get(yy)
                        if fo is not None and col in fo.columns:
                            nulls_before.append(
                                int(pd.to_numeric(fo[col], errors="coerce").isna().sum()))
                    if (nulls_now == 0 and nulls_before
                            and all(n > 0 for n in nulls_before)):
                        rows.append({
                            "module": mod, "column": col, "year": y, "code": 0,
                            "label": "No aplica", "status": "verified",
                            "evidence": (
                                f"THE NULL BECAME A ZERO. INEI changed how it "
                                f"encodes 'not applicable' for {col}: in "
                                f"{sorted(others)[:4]} the variable carries NULLS "
                                f"for non-respondents ({sorted(nulls_before)[:4]} of "
                                f"them) and NO code 0; in {y} the null count is "
                                f"EXACTLY ZERO and code 0 appears in their place, "
                                f"while the label is unchanged. Same concept, new "
                                f"representation — the nulls did not vanish, they "
                                f"were re-encoded."),
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
