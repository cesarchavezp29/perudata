"""Run the pooled canary across EVERY labelled variable. Keep passers, pull failers.

Loads each module-year ONCE and does all map-building and checking in memory (the
first version re-read every year for every variable -- 267 x 22 file loads for one
module).

MECHANICAL pass/fail. Needs no official number:
  * ROW COUNT preserved: no non-null raw value becomes null
  * DENOMINATOR preserved: an unlabelled code is a real category, never dropped
  * no year with usable raw data comes back all-NA        (the 2019 signature)
  * per-year distribution matches the raw column EXACTLY, share for share, only the
    ids move. ZERO tolerance: a pure remap changes no count, so ANY drift means a
    category merged or split -> FAIL.                     (the 100%-SIS signature)

PASSED -> 'stabilized'  (denominator-preserving, code-anchored; still UNVALIDATED
                         against any official figure)
FAILED -> pulled; left as 'detected' only.
"""
import json
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")

import pandas as pd  # noqa: E402

from perudata import dictionary as dic  # noqa: E402
from perudata import enaho  # noqa: E402

HERE = Path(__file__).parent
D = dic.all()
OVERRIDES_PATH = Path(__file__).parents[1] / "src/perudata/crosswalks/enaho_label_overrides.csv"
OVERRIDES = pd.read_csv(OVERRIDES_PATH, dtype={"module": str, "column": str}) if OVERRIDES_PATH.exists() else pd.DataFrame()
if not OVERRIDES.empty:
    OVERRIDES["module"] = OVERRIDES["module"].str.zfill(2)
    OVERRIDES = OVERRIDES[OVERRIDES["status"] == "verified"]
ONLY_MODULES = {m.zfill(2) for m in os.environ.get("PERUDATA_MODULES", "").split(",") if m}

# These are official classification-code namespaces, not ordinary categoricals.
# INEI identifies the standard in the variable label in every year. Within one
# declared revision, the code itself is the category identity; embedded SPSS/Stata
# value-label text is optional metadata. Revisions remain separate intentionally.
CLASSIFICATION_NAMESPACE = {
    "ocupac_r3": "CIOU-88",
    "ocupac_r4": "CNO-2015",
    "rama_3": "CIIU-R3",
    "rama_r3": "CIIU-R3",
    "rama_4": "CIIU-R4",
    "rama_r4": "CIIU-R4",
}


def norm_exact(s):
    """Accents/punctuation only. KEEPS the parenthetical."""
    t = unicodedata.normalize("NFKD", str(s).lower().strip())
    t = "".join(ch for ch in t if ch.isascii())
    t = re.sub(r"[^a-z0-9() ]", " ", t)
    return " ".join(t.split())


def norm_loose(s):
    """ALSO strips the parenthetical. Used ONLY as a fallback.

    Stripping '(SIS)' is what let 'seguro integral de salud' align across years.
    But in long category lists the parenthetical is the DISTINGUISHING part --
    'empresa de servicios especiales' vs '... (service)' are DIFFERENT categories,
    and collapsing them merged two codes onto one id (all 29 filter failures).
    So: match EXACT first, and fall back to loose only when exact finds nothing.
    """
    t = norm_exact(s)
    t = re.sub(r"\(.*?\)", " ", t)
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return " ".join(t.split())


results, maps = [], {}
stats = Counter()

for mod in sorted(D.module.unique()):
    if ONLY_MODULES and mod not in ONLY_MODULES:
        continue
    sub = D[D.module == mod]
    labels_by = {}          # (col, year) -> {code: normlabel}
    for _, r in sub.iterrows():
        vl = (json.loads(r["value_labels"])
              if isinstance(r["value_labels"], str) and r["value_labels"] else {})
        if vl:
            labels_by[(r["column"], int(r["year"]))] = {
                int(float(k)): (norm_exact(v), norm_loose(v)) for k, v in vl.items()}
    if not OVERRIDES.empty:
        ov = OVERRIDES[OVERRIDES["module"] == mod]
        for _, r in ov.iterrows():
            key = (r["column"], int(r["year"]))
            exact, loose = norm_exact(r["label"]), norm_loose(r["label"])
            labels_by.setdefault(key, {})[int(r["code"])] = (exact, loose)
    cand = sorted({c for c, _ in labels_by})
    years = [y for y in enaho.years() if enaho.path(y, mod).exists()]
    if not cand or not years:
        continue

    # ONE pass over the data: observed code set + value counts per (col, year)
    obs, cnts, raw_counts = {}, {}, {}
    for y in years:
        # Read only labelled candidates present in this module-year. Wide files
        # otherwise decode thousands of irrelevant columns before validation.
        available_y = set(sub.loc[sub["year"] == y, "column"])
        cols_y = [c for c in cand if c in available_y]
        if not cols_y:
            continue
        try:
            f = enaho.load(y, mod, columns=cols_y, download_if_missing=False)
        except Exception:
            continue
        for c in cand:
            if c not in f.columns:
                continue
            v = pd.to_numeric(f[c], errors="coerce").dropna()
            if v.empty:
                continue
            u = {int(x) for x in v.unique()} if (v % 1 == 0).all() else set()
            # A VARIABLE IS NOT A CATEGORICAL JUST BECAUSE ITS SIBLINGS ARE LABELLED.
            # `cand` is every variable INEI ever labelled anywhere, which sweeps in
            # three shapes that must never receive a label:
            #  * MEASUREMENTS. p5561c holds 20/40/50/70/80/100 — quantities. Its
            #    siblings p5561a (si/no) and p5561b (diario/semanal) ARE categorical,
            #    which is why it got dragged in.
            #  * CLASSIFICATION NAMESPACES. p505/p506 carry 4-digit CIIU/CIUO codes
            #    (7526, 6199): the code IS the identity per the published standard.
            #  * CORRUPTION. p207 (sex) holds ONE row at -126 in 2009 — a Stata int8
            #    overflow (-128..127), not a third sex. Labelling it invents data.
            if not u or any(x < 0 for x in u) or max(u) > 99 or len(u) > 30:
                continue
            obs[(c, y)] = u
            vc = v.value_counts()
            cnts[(c, y)] = sorted(vc.values.tolist())
            raw_counts[(c, y)] = {int(k): int(n) for k, n in vc.items()}
        del f
    print(f"--- module {mod}: {len(cand)} labelled vars, {len(years)} years",
          flush=True)

    for col in cand:
        yrs = sorted(y for (c, y) in obs if c == col)
        if not yrs:
            stats["NO_OBSERVED_DATA"] += 1
            results.append({"module": mod, "column": col,
                            "verdict": "NO_OBSERVED_DATA",
                            "reason": "column has no non-null raw observations in available years",
                            "years": 0, "ref_year": ""})
            continue
        # A variable observed in only one year still has a fully defined mapping
        # for its actual support. It is not skipped; absent years are genuine
        # no-data years and become NA only through stable-schema pooling.
        if col in CLASSIFICATION_NAMESPACE:
            # The namespace + code is the official identity. This resolves absent
            # embedded labels without guessing a textual occupation/industry name.
            ns = CLASSIFICATION_NAMESPACE[col]
            labelled = {
                y: {c: (norm_exact(f"{ns} {c}"), norm_loose(f"{ns} {c}"))
                    for c in obs[(col, y)]}
                for y in yrs
            }
        else:
            labelled = {y: labels_by[(col, y)] for y in yrs
                        if (col, y) in labels_by}
        missing_label_years = [y for y in yrs if y not in labelled]
        missing_code_labels = {
            y: sorted(obs[(col, y)] - set(labelled[y]))
            for y in labelled
            if obs[(col, y)] - set(labelled[y])
        }
        if missing_label_years or missing_code_labels:
            reason = []
            if missing_label_years:
                reason.append(f"years without value labels: {missing_label_years}")
            if missing_code_labels:
                reason.append(f"observed codes without labels: {missing_code_labels}")
            stats["UNRESOLVED_MAPPING"] += 1
            results.append({"module": mod, "column": col,
                            "verdict": "UNRESOLVED_MAPPING",
                            "reason": "; ".join(reason),
                            "years": len(yrs), "ref_year": ""})
            continue
        ref = max(labelled)
        if col in CLASSIFICATION_NAMESPACE:
            # A code does not change identity because it is absent from the latest
            # sample. Identity is namespace + code over the union of all years.
            all_codes = set().union(*(obs[(col, y)] for y in yrs))
            canon = {c: c for c in all_codes}
            ns = CLASSIFICATION_NAMESPACE[col]
            ref_lab = {
                c: (norm_exact(f"{ns} {c}"), norm_loose(f"{ns} {c}"))
                for c in all_codes
            }
        else:
            canon = {c: c for c in obs[(col, ref)]}
            ref_lab = labelled.get(ref, {})
        nxt = (max(canon.values()) if canon else 0) + 1

        m = {ref: dict(canon)}
        for y in yrs:
            if y == ref:
                continue
            ym, taken = {}, set()
            for c in sorted(obs[(col, y)]):
                lab = labelled.get(y, {}).get(c)
                hit = None
                if lab:
                    # TIER 1: EXACT label match (parenthetical kept)
                    for rc, rl in ref_lab.items():
                        if rl[0] and rl[0] == lab[0] and rc not in taken:
                            hit = rc
                            break
                    # TIER 2: loose match ONLY if exact found nothing
                    if hit is None:
                        for rc, rl in ref_lab.items():
                            if rl[1] and rl[1] == lab[1] and rc not in taken:
                                hit = rc
                                break
                if hit is None and c in canon and c not in taken:
                    hit = canon[c]                       # IDENTITY = the CODE
                if hit is None:                          # NEVER DROP: new category
                    hit = nxt
                    nxt += 1
                ym[c] = hit
                taken.add(hit)                           # injective by construction
            m[y] = ym
        verdict, reason = "VERIFIED_MAPPING", ""
        for y in yrs:
            mm = m.get(y)
            if not mm:
                verdict, reason = "FAILED", f"{y}: usable raw data -> all-NA"
                break
            missing = obs[(col, y)] - set(mm)
            if missing:
                verdict, reason = "FAILED", f"{y}: codes {sorted(missing)} dropped"
                break
            # ZERO TOLERANCE, and computed for real (the previous line compared a
            # value to ITSELF and could never fire -- a dead check that looks alive).
            # A map that is TOTAL (no code dropped) and INJECTIVE (no two codes onto
            # one id) preserves the value-count multiset exactly, by construction.
            # Assert it rather than assume it.
            if len(set(mm.values())) != len(mm):
                verdict, reason = "FAILED", f"{y}: two codes merge into one id"
                break
            remapped = Counter()
            for code, n in raw_counts[(col, y)].items():
                remapped[mm[code]] += n
            if sorted(remapped.values()) != sorted(raw_counts[(col, y)].values()):
                verdict, reason = "FAILED", f"{y}: distribution changed (share drift)"
                break
        results.append({"module": mod, "column": col, "verdict": verdict,
                        "reason": reason, "years": len(yrs), "ref_year": ref})
        stats[verdict] += 1
        if verdict == "VERIFIED_MAPPING":
            maps.setdefault(mod, {})[col] = {
                "map": {str(y): {str(k): int(v) for k, v in mm.items()}
                        for y, mm in m.items()},
                "labels": {str(canon.get(c, c)): l
                           for c, l in ref_lab.items()},
            }

r = pd.DataFrame(results)
r.to_csv(HERE / "recode_filter_results.csv", index=False)
(HERE / "recodes_passed.json").write_text(json.dumps(maps, ensure_ascii=False),
                                          encoding="utf-8")
print()
for k, v in stats.most_common():
    print(f"   {k:32s} {v:,}")
print(f"\nVERIFIED maps kept: {sum(len(v) for v in maps.values()):,}")




