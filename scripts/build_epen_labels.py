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


_VAR = re.compile(r"^([A-Z][A-Z0-9_]+)\s+\d+\s+[NC]\b")
# a value label: 'code label' or 'code. label' -- the modern dict uses the dot
_VAL = re.compile(r"^(\d+)\.?\s+(\S.*)$")


def parse_pdf(path: Path) -> dict:
    """{variable: {code: label}} from an EPEN Diccionario PDF.

    Format (both eras): a variable header 'C306_4 1 N <label...>' followed by
    value-label lines '1 Si' / '2 No' and a 'Rango : (1:2)'. The modern c-series
    (C306_*, OCUP300, ...) lives ONLY in these PDFs -- the CSVs carry no labels.
    """
    import pdfplumber
    out: dict = {}
    try:
        with pdfplumber.open(str(path)) as pdf:
            lines = []
            for pg in pdf.pages:
                lines += (pg.extract_text() or "").splitlines()
    except Exception:
        return out
    cur = None
    for ln in lines:
        s = ln.strip()
        m = _VAR.match(s)
        if m:
            cur = m.group(1).lower()
            out.setdefault(cur, {})
            continue
        if cur is None:
            continue
        if s.lower().startswith("rango"):
            cur = None                       # value labels end at the Rango line
            continue
        v = _VAL.match(s)
        if v:
            code, lab = v.group(1), v.group(2).strip()
            # a value code is small (0-99); >=100 is a question number wrapping
            # into the value block, and its 'label' is question text, not a value
            if int(code) < 100 and 0 < len(lab) <= 55:
                out[cur].setdefault(code, lab)
    return out


def main() -> int:
    savs = sorted(set(p.resolve() for p in
                      list(RAW.rglob("*.sav")) + list(RAW.rglob("*.SAV"))))
    print(f"EPEN .sav files found: {len(savs)}")

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

    # the modern c-series labels come ONLY from the dictionary PDFs. Parse one of
    # each UNIQUE dictionary (many departments ship the same 2023 dict).
    pdfs = list(RAW.rglob("*iccionario*.pdf")) + list(RAW.rglob("*iccionario*.PDF"))
    seen_names, pdf_read = set(), 0
    for p in sorted(pdfs):
        tag = (p.name.lower(), p.stat().st_size // 1000)
        if tag in seen_names:
            continue
        seen_names.add(tag)
        for var, codes in parse_pdf(p).items():
            d = acc.setdefault(var, {})
            for code, lab in codes.items():
                d.setdefault(code, {}).setdefault(lab, 0)
                d[code][lab] += 1
        pdf_read += 1
    print(f"unique dictionary PDFs parsed: {pdf_read}")

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
