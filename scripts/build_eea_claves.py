"""Harvest the EEA Clave -> concept map from the sector dictionary PDFs.

EEA is firm accounting: each financial chapter (c02 Balance, c03 Estado de
Producción, c09 Gastos de Personal, c10 Personal Ocupado, ...) stores its lines
under a numeric `Clave`, and the concept each Clave means is NOT in the data --
it is in `Diccionario_Variables_s<sector>_f<form>_EEA<year>.pdf`. The dictionary
lists, per line, '<PCGE code> <concept> <Clave>' (the LAST number is the Clave),
e.g. '82 VALOR AGREGADO (38-87) 88' -> Clave 88 = Valor Agregado.

Claves are reused across chapters, and concepts vary by sector/formulario, so the
map is keyed by (year, sector, formulario, clave). This writes
crosswalks/eea_clave_concept.csv so eea.clave_concept() can name a Clave.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import pandas as pd  # noqa: E402

RAW = Path(os.environ.get("EEA_RAW", r"D:\ENAHO_ANALYSIS\raw\eea_inei"))
OUT = Path(__file__).parents[1] / "src" / "perudata" / "crosswalks"

# '<pcge> <concept ...> <clave>' -- capture concept and the trailing Clave
_LINE = re.compile(r"^(\d\S*)\s+(.+?)\s+(\d{1,3})$")
_META = re.compile(r"s(\d+)_f([A-Za-z0-9]+)_EEA(\d{4})", re.I)
# chapter section header inside the dict: 'a2023_s04_fF2_c03_1 TABLA QUE CONTIENE'
_CHAP = re.compile(r"_c(\w+?)_\d+\s+TABLA QUE CONTIENE", re.I)


def main() -> int:
    pdfs = list(RAW.rglob("Diccionario_Variables_*.pdf"))
    print(f"EEA dictionary PDFs: {len(pdfs)}")
    import pdfplumber

    rows, seen = [], set()
    for p in sorted(pdfs):
        m = _META.search(p.name)
        if not m:
            continue
        sector, form, year = m.group(1).zfill(2), m.group(2), int(m.group(3))
        if (sector, form, year) in seen:
            continue
        seen.add((sector, form, year))
        try:
            with pdfplumber.open(str(p)) as pdf:
                lines = []
                for pg in pdf.pages:
                    lines += (pg.extract_text() or "").splitlines()
        except Exception:
            continue
        chap = None
        for ln in lines:
            s = ln.strip()
            ch = _CHAP.search(s)
            if ch:
                chap = "c" + ch.group(1).lower()
                continue
            g = _LINE.match(s)
            if not g:
                continue
            concept, clave = g.group(2).strip(), g.group(3)
            # concept must be textual (skip pure-number / formula-only rows)
            if len(concept) < 3 or not re.search(r"[A-Za-zÁÉÍÓÚÑ]", concept):
                continue
            rows.append({"year": year, "sector": sector, "formulario": form,
                         "chapter": chap, "clave": clave, "concepto": concept})

    t = pd.DataFrame(rows).drop_duplicates(
        subset=["year", "sector", "formulario", "chapter", "clave", "concepto"])
    t.to_csv(OUT / "eea_clave_concept.csv", index=False, encoding="utf-8")
    print(f"dictionaries parsed: {len(seen)}")
    print(f"(year, sector, form, chapter, clave, concept) rows: {len(t):,}")
    print(f"  distinct claves: {t.clave.nunique()}  chapters: "
          f"{sorted(t.chapter.dropna().unique())[:12]}")
    va = t[t.concepto.str.fullmatch(r"VALOR AGREGADO.*", case=False, na=False)]
    print(f"  VALOR AGREGADO located: chapters {sorted(va.chapter.dropna().unique())}, "
          f"claves {sorted(va.clave.unique())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
