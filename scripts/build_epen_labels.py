"""Harvest EPEN value labels from the .sav era into a canonical crosswalk.

EPEN ships as CSV (codes only, no labels) for most of its span, but the legacy
EPE Lima .sav files (2001-2015) carry embedded value labels. Harvest every one,
canonicalize per (variable, code) to the most complete Spanish label, and write
crosswalks/epen_label_canon.csv. epen.value_labels() serves it so a coded CSV
column can be decoded.

NOTE (honest scope): the .sav era uses the LEGACY p-series variable names
(p203, ocu200, p207a); the modern EPEN CSV era renamed them to a c-series
(c201, ocup300). So these labels cover the p-series directly; mapping them onto
the modern c-series needs a variable-name crosswalk from the EPEN questionnaire
(a follow-up). What ships here is the verified label set for every variable the
.sav files actually carry.
"""
import os
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import pandas as pd  # noqa: E402
import pyreadstat  # noqa: E402

OUT = Path(__file__).parents[1] / "src" / "perudata" / "crosswalks"
RAW = Path(os.environ.get("EPEN_RAW", r"D:\ENAHO_ANALYSIS\raw\epen_inei"))


def codekey(c) -> str:
    try:
        f = float(c)
        return str(int(f)) if f.is_integer() else str(f)
    except (ValueError, TypeError):
        return str(c)


def nz(x: str) -> str:
    x = unicodedata.normalize("NFKD", str(x))
    return "".join(c for c in x if not unicodedata.combining(c)).lower().strip()


def main() -> int:
    savs = sorted(RAW.rglob("*.sav")) + sorted(RAW.rglob("*.SAV"))
    savs = sorted(set(p.resolve() for p in savs))
    print(f"EPEN .sav files found: {len(savs)}")

    # variable -> code -> {label: count} across all files (pick the most common,
    # longest label as canonical)
    acc: dict = {}
    read = 0
    for p in savs:
        try:
            _, meta = pyreadstat.read_sav(str(p), metadataonly=True)
        except Exception:
            continue
        read += 1
        for var, vals in meta.variable_value_labels.items():
            d = acc.setdefault(var.lower(), {})
            for c, lab in vals.items():
                d.setdefault(codekey(c), {}).setdefault(lab, 0)
                d[codekey(c)][lab] += 1

    rows = []
    for var in sorted(acc):
        for code in acc[var]:
            variants = acc[var][code]
            # canonical: most frequent, then longest (most complete) label
            canon = sorted(variants, key=lambda s: (-variants[s], -len(s)))[0]
            rows.append({"variable": var, "code": code, "label": canon,
                         "n_files": sum(variants.values()),
                         "n_variants": len(variants)})
    t = pd.DataFrame(rows).sort_values(["variable", "code"])
    t.to_csv(OUT / "epen_label_canon.csv", index=False, encoding="utf-8")

    print(f"read {read} .sav files")
    print(f"canonical (variable, code) labels: {len(t):,} "
          f"over {t.variable.nunique():,} variables")
    drift = t[t.n_variants > 1]
    print(f"  codes with >1 label variant across files (reconciled): {len(drift):,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
