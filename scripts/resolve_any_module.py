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


CATEGORY = re.compile(r"^\s*(\d{1,4})\s*[.\-]?\s*([A-Za-zÁÉÍÓÚÑáéíóúñ¿(].*?)\s*$")


_DICT_CACHE: dict = {}


def dictionary_tables(year: int, module: str) -> tuple[dict, dict]:
    """({VAR: {code: label}}, {VAR: (lo, hi)}) from INEI's published dictionary.

    THE TABLE, not merely the declared range. INEI's 2015 dictionary states
    "P5401A ... 0 Pase / 1 Diario / 2 Semanal / ..." -- code 0 is DOCUMENTED, in
    black and white. Reading only the Rango line threw that away and left the
    variable unresolved for want of a label INEI had already written.
    """
    # CACHE IT. This is called per (column, year), so module 03 re-parsed a
    # ~350k-char dictionary 650 x 22 = 14,300 times. That is what was making the
    # runs take forever and get killed before they finished -- not the data.
    key = (year, module)
    if key in _DICT_CACHE:
        return _DICT_CACHE[key]
    for p in (SRC / "inzip" / f"{year}_{module}.txt",
              SRC / f"ENAHO_{year}_Diccionario.txt"):
        if not p.exists():
            continue
        tab, rng, cur = {}, {}, None
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            h = HEADER.match(line)
            if h:
                cur = h.group(1).lower()
                tab.setdefault(cur, {})
                continue
            if cur is None:
                continue
            r = RANGE.match(line)
            if r:
                rng[cur] = (int(r.group(1)), int(r.group(2)))
                cur = None
                continue
            c = CATEGORY.match(line)
            if c:
                code, lab = int(c.group(1)), c.group(2).strip()
                if lab and not lab[0].isdigit():
                    tab[cur].setdefault(code, lab)
        tab = {k: v for k, v in tab.items() if v}
        if tab or rng:
            _DICT_CACHE[key] = (tab, rng)
            return tab, rng
    _DICT_CACHE[key] = ({}, {})
    return {}, {}


def declared_ranges(year: int, module: str) -> dict:
    return dictionary_tables(year, module)[1]


def labelled_columns(year: int, mod: str) -> set[str] | None:
    """Columns that COULD carry a value label -- from the .dta's own metadata
    and the published dictionary -- known without reading a single data row.

    The consumption and production modules (07-28) are item-level long files:
    module 07 is 9.1M rows x 22 years, which OOMs if every year's full frame is
    held at once. But those modules are almost all continuous amounts; only a
    handful of columns are categorical (module 77 had 7 of 46). A continuous
    'gasto' column carries no value label and no categorical dictionary entry,
    so restricting the load to label-bearing columns drops the memory by orders
    of magnitude and cannot lose a resolvable variable: a code with no label in
    any .dta AND no dictionary row is declined regardless. Structural keys are
    always kept so the behavioural proofs (universe, complementarity) still run.
    """
    keep = {"conglome", "vivienda", "hogar", "codperso", "ubigeo", "mes",
            "dominio", "estrato"}
    try:
        import pyreadstat
        p = enaho.path(year, mod)
        _, meta = pyreadstat.read_dta(str(p), metadataonly=True)
        present = {c.lower() for c in meta.column_names}
        keep |= {c.lower() for c in meta.variable_value_labels}
    except Exception:
        return None                      # can't introspect -> load everything
    keep |= set(dictionary_tables(year, mod)[0])   # dict-documented columns
    return keep & present                # only ask for columns this year has


_PRESENT_CACHE: dict = {}


def _present_cols(year: int, mod: str) -> set[str]:
    """Lower-cased column names in a year's .dta, from metadata only."""
    key = (year, mod)
    if key not in _PRESENT_CACHE:
        import pyreadstat
        _, meta = pyreadstat.read_dta(str(enaho.path(year, mod)),
                                      metadataonly=True)
        _PRESENT_CACHE[key] = {c.lower() for c in meta.column_names}
    return _PRESENT_CACHE[key]


FRUGAL = os.environ.get("PERUDATA_FRUGAL") == "1"

rows, declined = [], []
for mod in MODULES:
    years = [y for y in enaho.years() if enaho.path(y, mod).exists()]
    if not years:
        continue
    frames, labels = {}, {}
    # A column INEI labels in only ONE year must still be loaded in EVERY year,
    # or the cross-year rules (phantom, carry-forward, flag-battery) see a
    # truncated code history. So the frugal allow-list is the UNION over all
    # years, applied uniformly -- never a per-year filter.
    use_all, present = None, {}
    if FRUGAL:
        use_all = set()
        for y in years:
            got = labelled_columns(y, mod)
            if got is None:
                use_all = None          # any un-introspectable year -> load all
                break
            use_all |= got
            present[y] = _present_cols(y, mod)
    for y in years:
        try:
            if use_all is not None:
                frames[y] = enaho.load(y, mod, download_if_missing=False,
                                       columns=sorted(use_all & present[y]))
            else:
                frames[y] = enaho.load(y, mod, download_if_missing=False)
        except Exception:
            continue
    cols = sorted({c for f in frames.values() for c in f.columns})
    print(f"--- module {mod}: {len(cols)} columns, {len(frames)} years"
          f"{' [frugal]' if FRUGAL else ''}", flush=True)

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
            tables, ranges = dictionary_tables(y, mod)
            lo_hi = ranges.get(col)
            dict_tab = tables.get(col, {})
            for code in sorted(missing):
                # RULE 0: INEI ALREADY WROTE IT DOWN. Check the published category
                # table for THIS year before inferring anything at all. p5401a's
                # 2015 dictionary literally says "0 Pase".
                if code in dict_tab:
                    rows.append({
                        "module": mod, "column": col, "year": y, "code": code,
                        "label": dict_tab[code].strip().capitalize(),
                        "status": "verified",
                        "evidence": (
                            f"INEI's official {y} Diccionario de Datos states it "
                            f"outright: '{col.upper()} ... {code} "
                            f"{dict_tab[code]}'. The .dta simply omits the value "
                            f"label that the published dictionary carries. Exact "
                            f"year, exact variable, exact code."),
                    })
                    continue
                # RULE 3: does INEI name this code in ANY other year?
                #
                # Look in BOTH places INEI writes labels: the .dta value labels AND
                # the published dictionary tables. INEI's 2015 dictionary documents
                # "P5401A ... 0 Pase", while the 2024/2025 dictionaries drop that
                # line and start at "1. Diario" -- yet the data still ships code 0.
                # INEI stopped DOCUMENTING a code it never stopped USING. Consulting
                # only .dta labels missed it, because the evidence was in the
                # dictionary of a different year.
                elsewhere = {yy: m[code] for yy, m in lab.items()
                             if code in m and yy != y}
                for yy in sorted(obs):
                    if yy == y or yy in elsewhere:
                        continue
                    t, _r = dictionary_tables(yy, mod)
                    if code in t.get(col, {}):
                        elsewhere[yy] = t[col][code]
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
                            f"{sorted(elsewhere)} as '{elsewhere[src]}' — in its "
                            f"own .dta value labels and/or its published "
                            f"Diccionario de Datos. Same variable, same code, same "
                            f"concept: INEI stopped DOCUMENTING the code, it did "
                            f"not stop USING it."),
                    })
                    continue
                # RULE 7: THE COMPLEMENTARY PAIR. Two columns share one label set
                # and are MUTUALLY EXCLUSIVE: exactly one of them carries the
                # answer and the other sits at 0. Code 0 means "the answer is in the
                # other column", not a category.
                # PROVEN on module 05's b/d frequency pairs: exactly ONE set in
                # 12,782 / 21,864 / 46,433 cases across 2004/2015/2020, against only
                # 36-78 where BOTH are set (0.2-0.6%). p5563d==0 -> p5563b holds the
                # frequency (4=mensual, 2,997 rows); p5563d 1-8 -> p5563b==0.
                if code == 0 and re.fullmatch(r"(p\d+)([bd])", col):
                    stem, suf = re.fullmatch(r"(p\d+)([bd])", col).groups()
                    twin = f"{stem}{'b' if suf == 'd' else 'd'}"
                    fy = frames.get(y)
                    if fy is not None and twin in fy.columns and col in fy.columns:
                        a = pd.to_numeric(fy[col], errors="coerce").fillna(-1)
                        b = pd.to_numeric(fy[twin], errors="coerce").fillna(-1)
                        both = int(((a > 0) & (b > 0)).sum())
                        one = int(((a > 0) ^ (b > 0)).sum())
                        exclusive = (both == 0 and one >= 20) or (
                            one > 100 and both < 0.02 * max(one, 1))
                        if exclusive:
                            rows.append({
                                "module": mod, "column": col, "year": y, "code": 0,
                                "label": "No corresponde a esta columna",
                                "status": "verified",
                                "evidence": (
                                    f"COMPLEMENTARY PAIR, proven by mutual "
                                    f"exclusivity. {col} and {twin} share one label "
                                    f"set and exactly ONE of them carries the "
                                    f"answer: in {y}, {one:,} rows have exactly one "
                                    f"set against only {both:,} with both "
                                    f"({100 * both / max(one, 1):.2f}%). So code 0 "
                                    f"means 'the answer is in {twin}', not a "
                                    f"category of its own."),
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
                # A PHANTOM LABEL MUST NOT VETO THIS RULE. p3152 is {0,1} in the
                # data with label {1: 'autosuministro'} -- a textbook flag -- but its
                # 2009-2012 labels name code 2, which exists in NO year (p3152 is the
                # 2nd slot of its battery, the same INEI bug as p1142/p1144). Judging
                # the rule on `lab.values()` let a label INEI got WRONG outvote four
                # correct ones. Consult only the years whose labels match the data.
                trusted = good or lab
                if (code == 0 and all_obs <= {0, 1} and trusted
                        and all(set(m) == {1} for m in trusted.values())):
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
                # The precondition is about NULLS, not code sets. Defining "other
                # years" as those WITHOUT code 0 fails on p55610d, where code 0 is
                # present in every year and the comparison set comes out empty --
                # even though the null counts show the re-encoding plainly:
                # 92,038 / 91,250 / 86,580 nulls in 2019-2023, then EXACTLY 0 in
                # 2024/2025. Compare years by their null counts instead.
                if code == 0 and y in obs:
                    fy = frames.get(y)
                    nulls_now = int(pd.to_numeric(fy[col], errors="coerce").isna().sum()) \
                        if fy is not None and col in fy.columns else -1
                    nulls_by_year = {}
                    for yy in obs:
                        fo = frames.get(yy)
                        if fo is not None and col in fo.columns:
                            nulls_by_year[yy] = int(
                                pd.to_numeric(fo[col], errors="coerce").isna().sum())
                    others = sorted(yy for yy, n in nulls_by_year.items() if n > 0)
                    nulls_before = [nulls_by_year[yy] for yy in others]
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
                # LAST RESORT, and it must stay last. A code carried by ONE row
                # in ~85,000 (0.001%) is a data-entry or encoding artifact -- the
                # same class as p207's single -126 (a Stata int8 overflow, not a
                # third sex). estrsocial code 6 was certifiable precisely BECAUSE
                # 12,952 records made a deterministic statement possible; one row
                # makes no statement at all.
                # BUT THIS IS A HEURISTIC, AND EVIDENCE BEATS A HEURISTIC. Running it
                # FIRST (as it was) threw away 1-row codes that INEI's own dictionary
                # explicitly labels -- declining as "noise" something INEI had
                # written down. Every rule above gets its chance first.
                fy = frames.get(y)
                n_rows = (int((pd.to_numeric(fy[col], errors="coerce") == code).sum())
                          if fy is not None and col in fy.columns else 0)
                if 0 < n_rows <= 5:
                    declined.append({
                        "module": mod, "column": col, "year": y, "code": code,
                        "why": (f"single-row noise: {n_rows} row(s) of {len(fy):,} "
                                f"({100 * n_rows / len(fy):.4f}%), and NO rule could "
                                f"certify it — a data-entry/encoding artifact. One "
                                f"observation cannot establish a meaning.")})
                    continue
                declined.append({"module": mod, "column": col, "year": y,
                                 "code": code,
                                 "why": "no label in any year, and not inside a "
                                        "declared range — needs its own evidence"})

KEY = ["module", "column", "year", "code"]
new = pd.DataFrame(rows).drop_duplicates(subset=KEY).astype(str)
old = pd.read_csv(OUT, encoding="utf-8-sig", dtype=str)

# THE CROSSWALK WAS APPEND-ONLY AND COULD NOT SELF-CORRECT. concat([old, new])
# + keep="first" let a row written by an EARLIER, WORSE rule silently outrank the
# rule that supersedes it: p3152's code 0 was labelled "Pase" by rule 1 for
# 2007-2020 and "No marcado" by rule 5 for 2021-2025 -- the SAME code in the SAME
# column meaning two different things, which is the exact defect harmonizing
# exists to remove. Never silently keep either side: REPORT every disagreement
# and let evidence decide.
d = old.merge(new, on=KEY, how="inner", suffixes=("_old", "_new"))
d = d[d.label_old != d.label_new]
d.to_csv(Path(__file__).parent / "override_disagreements.csv", index=False,
         encoding="utf-8")
if len(d):
    print(f"!! {len(d):,} rows where the rules now disagree with the shipped "
          f"crosswalk (scripts/override_disagreements.csv)")
    for (lo, ln), g in d.groupby(["label_old", "label_new"]):
        print(f"     {lo!r} -> {ln!r}: {len(g):,} rows, "
              f"{g.column.nunique()} columns")

both = pd.concat([old, new], ignore_index=True).drop_duplicates(
    subset=KEY, keep="first")
both.to_csv(OUT, index=False, encoding="utf-8")
print()
print(f"certified: {len(new):,}   (by rule: "
      f"{dict(Counter(r['evidence'][:24] for r in rows))})")
print(f"DECLINED (reported, never invented): {len(declined):,}")
print(f"override rows: {len(old):,} -> {len(both):,}")
if declined:
    pd.DataFrame(declined).to_csv(Path(__file__).parent / "declined_codes.csv",
                                  index=False)
