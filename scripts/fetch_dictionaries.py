"""Fetch INEI's official ENAHO data dictionaries for the years we lack.

Two URL shapes are known to work (found by Codex), and INEI is not consistent
about which year lives where, so try both and verify what comes back is actually
a PDF -- INEI answers a miss with an HTML page under HTTP 200, and a 200 is not
proof of a document.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from perudata import _core  # noqa: E402

OUT = Path(__file__).parents[1] / "docs" / "source"
OUT.mkdir(parents=True, exist_ok=True)

PATTERNS = [
    "https://www.inei.gob.pe/media/DATOS_ABIERTOS/ENAHO/DICCIONARIO/{y}/Anual/Diccionario.pdf",
    "https://www.inei.gob.pe/media/DATOS_ABIERTOS/ENAHO/DICCIONARIO/{y}/Diccionario.pdf",
    "https://proyectos.inei.gob.pe/iinei/srienaho/Descarga/DocumentosMetodologicos/{y}-55/Diccionario.pdf",
]

want = [int(a) for a in sys.argv[1:]] or [
    2005, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2020, 2024, 2025]

got, missing = [], []
for y in want:
    dest = OUT / f"ENAHO_{y}_Diccionario.pdf"
    if dest.exists() and dest.stat().st_size > 100_000:
        print(f"[have] {y}")
        got.append(y)
        continue
    for pat in PATTERNS:
        url = pat.format(y=y)
        blob = _core.get(url, timeout=180, tries=2)
        # a 200 is not proof: INEI serves an HTML page for a miss
        if blob and blob[:4] == b"%PDF" and len(blob) > 100_000:
            dest.write_bytes(blob)
            print(f"[ok  ] {y}: {len(blob)/1e6:.1f} MB  <- {url}")
            got.append(y)
            break
    else:
        print(f"[MISS] {y}: no pattern served a PDF")
        missing.append(y)

print(f"\nhave: {sorted(got)}")
print(f"missing: {sorted(missing)}")
