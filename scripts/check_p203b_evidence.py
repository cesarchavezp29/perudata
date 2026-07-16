"""Print deterministic same-year evidence for undocumented P203B codes."""
import os

import pandas as pd

os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")

from perudata import enaho  # noqa: E402


for year in range(2018, 2026):
    frame = enaho.load(year, "02", download_if_missing=False)
    pair = frame[["p203", "p203b"]].apply(pd.to_numeric, errors="coerce")
    for code in (7, 11):
        rows = pair[pair["p203b"] == code]
        if not rows.empty:
            print(year, code, len(rows), rows["p203"].value_counts().to_dict())
