"""The last 14 of module 01. Each is a singleton: gather its evidence, then decide.

No family shortcut applies here. For each: what does the dictionary say, what does
the .dta label say in every year, and what does the DATA actually hold?
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
CASES = {
    "panel": (2004, 2005), "p613": (2004, 2005, 2006), "ticuest01": (2016,),
    "p111": (2011,), "p1138": (2007,), "p116a2": (2004,), "p116c": (2004,),
    "periodo": (2004, 2005, 2006), "t110": (2007,), "p113a": (2004, 2020),
    "p612i1": (2007, 2013), "p612i2": (2007, 2013), "p612i22": (2007, 2020),
    "p1175_02": (2025,),
}


def block(year: int, var: str, n: int = 7) -> str:
    for p in (SRC / f"ENAHO_{year}_Diccionario.txt", SRC / "inzip" / f"{year}_01.txt"):
        if not p.exists():
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(rf"^{re.escape(var.upper())}\s+\d+\s+\d+\s+[NAC]\s+.*$", t, re.M)
        if m:
            return "\n".join(t[m.start():].splitlines()[:n])
    return "(no dictionary block)"


for var, years in CASES.items():
    print("=" * 78)
    print(f"### {var}")
    print(block(years[0], var))
    print("-" * 30)
    for y in enaho.years():
        try:
            d = enaho.load(y, "01", download_if_missing=False)
        except Exception:
            continue
        if var not in d.columns:
            continue
        v = pd.to_numeric(d[var], errors="coerce")
        lab = dic.value_labels(var, y, "01")
        vc = v.value_counts().head(5).to_dict()
        flag = "  <-- BLOCKING" if y in years else ""
        print(f"   {y}: labels={lab} | top={vc}{flag}")
    print()
