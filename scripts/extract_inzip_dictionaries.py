"""Certify labels from the dictionaries INEI ships INSIDE each module zip.

These are the most authoritative source available: INEI packages the dictionary
next to the very .dta it documents, so it is per-year AND per-module, with no
guessing about which document belongs to which release. They are also the only
source for years whose standalone dictionary INEI does not publish at any known
URL (2025 is not on the open-data site; the `{year}-55` path serves EPEN instead).

Guards, each of which exists because it already went wrong once:
  * WRONG SURVEY: the zip is fetched by (year, module), so the document cannot be
    another survey's -- unlike the standalone URLs, where `2025-55` served EPEN.
    Still verified from the text ("Archivo: ENAHO01-2025-100").
  * PAGE FURNITURE: a page break drops "Diccionario de Datos / Encuesta Nacional
    de Hogares INEI / Variable Tamano Decimal Form Etiqueta" INTO the middle of a
    category table. Those lines must not end a block or be read as categories.
  * CROSS-CHECK: every code the dictionary gives is checked against the codes
    actually observed in that year's microdata; a code in the data but not the
    dictionary is REPORTED, never invented (INEI's own 2016 dictionary omits
    estrsocial code 6 while the data carries 12,952 of them).
"""
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")

import pandas as pd  # noqa: E402
import pdfplumber  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from perudata import _core, enaho  # noqa: E402

ROOT = Path(__file__).parents[1]
CACHE = ROOT / "docs" / "source" / "inzip"
CACHE.mkdir(parents=True, exist_ok=True)
OUT = ROOT / "src" / "perudata" / "crosswalks" / "enaho_label_overrides.csv"

HEADER = re.compile(r"^([A-Z][A-Z0-9_$]{1,12})\s+\d+\s+\d+\s+[NAC]\s+(.+?)\s*$")
CATEGORY = re.compile(r"^\s*(\d{1,4})\s*[.\-]?\s*([A-Za-zÁÉÍÓÚÑáéíóúñ¿(].*?)\s*$")
RANGE = re.compile(r"^\s*Rango\s*:\s*(\d+)\s*[-–]\s*(\d+)", re.I)
# page furniture that lands mid-table at a page break
NOISE = re.compile(r"^\s*(Diccionario de Datos|Encuesta Nacional de Hogares|"
                   r"Archivo:|Variable\s+Tama|ato\s*$|INEI\s*$|\d+\s*$)", re.I)


def pdf_text(year: int, module: str) -> str | None:
    """The dictionary INEI ships inside this (year, module) zip."""
    txt = CACHE / f"{year}_{module}.txt"
    if txt.exists():
        return txt.read_text(encoding="utf-8", errors="replace")
    try:
        zf = _core.fetch_zip(enaho.url(year, module))
    except Exception as e:  # noqa: BLE001
        print(f"[{year} M{module}] zip unavailable: {type(e).__name__}")
        return None
    names = [n for n in zf.namelist()
             if re.search(r"diccionario", n, re.I) and n.lower().endswith(".pdf")]
    if not names:
        return None
    dest = CACHE / f"_{year}_{module}.pdf"
    dest.write_bytes(zf.read(names[0]))
    try:
        with pdfplumber.open(dest) as d:
            t = "\n".join((p.extract_text() or "") for p in d.pages)
    except Exception:
        return None
    finally:
        dest.unlink(missing_ok=True)
    txt.write_text(t, encoding="utf-8")
    return t


def parse(text: str) -> tuple[dict, dict]:
    out, rng, cur = {}, {}, None
    for line in text.splitlines():
        if NOISE.match(line):
            continue                      # page furniture: never ends a block
        h = HEADER.match(line)
        if h:
            cur = h.group(1).lower()
            out.setdefault(cur, {})
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
                out[cur].setdefault(code, lab)
    return {k: v for k, v in out.items() if v}, rng


years = [int(a) for a in sys.argv[1:] if a.isdigit()] or list(enaho.years())
modules = os.environ.get("PERUDATA_MODULES", "01").split(",")

rows, gaps = [], []
for y in years:
    for mod in modules:
        t = pdf_text(y, mod)
        if not t:
            print(f"[{y} M{mod}] no dictionary in the zip")
            continue
        if "ENAHO" not in t[:6000].upper():
            print(f"[{y} M{mod}] the shipped document is NOT ENAHO — refused")
            continue
        dic, ranges = parse(t)
        try:
            df = enaho.load(y, mod, download_if_missing=False)
        except Exception:
            print(f"[{y} M{mod}] microdata not local")
            continue
        n = 0
        for col in df.columns:
            table = dic.get(col)
            if not table:
                continue
            v = pd.to_numeric(df[col], errors="coerce").dropna()
            if v.empty or not (v % 1 == 0).all():
                continue
            obs = {int(x) for x in v.unique()}
            if len(obs) > 30:
                continue
            missing = obs - set(table)
            if missing:
                lo, hi = ranges.get(col, (None, None))
                inr = lo is not None and all(lo <= c <= hi for c in missing)
                gaps.append({"year": y, "module": mod, "column": col,
                             "codes": str(sorted(missing)),
                             "why": "inside the declared range, unlabelled: INEI's "
                                    "`pase` convention" if inr else
                                    "outside the declared range: dictionary and "
                                    "released data disagree — reported"})
                continue
            for code in sorted(obs):
                rows.append({"module": mod, "column": col, "year": y, "code": code,
                             "label": table[code], "status": "verified",
                             "evidence": f"INEI Diccionario_{y}.pdf shipped INSIDE "
                                         f"the {y} Modulo{mod} zip (per-year, "
                                         f"per-module, packaged with the .dta it "
                                         f"documents); every observed code "
                                         f"cross-checked against the microdata"})
            n += 1
        print(f"[{y} M{mod}] {n} variables certified from the in-zip dictionary")

new = pd.DataFrame(rows)
if OUT.exists() and len(new):
    old = pd.read_csv(OUT, encoding="utf-8-sig", dtype=str)
    both = pd.concat([old, new.astype(str)], ignore_index=True).drop_duplicates(
        subset=["module", "column", "year", "code"], keep="first")
    both.to_csv(OUT, index=False, encoding="utf-8")
    print(f"\noverride rows total: {len(both):,} (added {len(both)-len(old):,})")
if gaps:
    pd.DataFrame(gaps).to_csv(Path(__file__).parent / "inzip_gaps.csv", index=False)
    print(f"reported, not invented: {len(gaps)} variable-years")
