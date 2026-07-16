"""What ARE the remaining module-01 families? Evidence before any certification.

Four fingerprints:
  p1175_* (15) code 0 in 2004-2007  -- the SPENDING battery. Is 0 `pase`, or is it
                                       "consumed but paid nothing"? Different meaning.
  p1171_* (14) no labels in 2004-2005
  p107a*  (6)  code 1 unlabelled 2007-2011 -- smells like the p114x phantom pattern
  singles: p111, p1138, p113a, p116a2, p116c, p613, panel, periodo, t110,
           ticuest01, p612i*
"""
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from perudata import dictionary as dic  # noqa: E402
from perudata import enaho  # noqa: E402

SRC = Path(__file__).parents[1] / "docs" / "source"


def dict_block(year: int, var: str, n: int = 8) -> str:
    for p in (SRC / f"ENAHO_{year}_Diccionario.txt",
              SRC / "inzip" / f"{year}_01.txt"):
        if not p.exists():
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(rf"^{var.upper()}\s+\d+\s+\d+\s+[NAC]\s+.*$", t, re.M)
        if m:
            return "\n".join(t[m.start():].splitlines()[:n])
    return "(no dictionary block found)"


for var, years in (("p1175_02", (2004, 2006, 2010, 2025)),
                   ("p1171_01", (2004, 2006, 2010)),
                   ("p107a21", (2007, 2008, 2012)),
                   ("p613", (2004, 2010))):
    print("=" * 78)
    print(f"### {var}")
    print(dict_block(min(years), var))
    print("-" * 40)
    for y in years:
        try:
            d = enaho.load(y, "01", download_if_missing=False, columns=[var])
        except Exception:
            continue
        v = pd.to_numeric(d[var], errors="coerce")
        vc = v.value_counts().head(6).to_dict()
        print(f"   {y}: labels={dic.value_labels(var, y, '01')} | "
              f"top values={vc} | nulls={int(v.isna().sum()):,}")
    print()
