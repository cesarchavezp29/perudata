"""Inspect remaining module-02 mappings against raw observations and metadata."""
import os
import pandas as pd
os.environ.setdefault("PERUDATA_DIR", r"D:\peru_raw_check")
from perudata import dictionary, enaho
checks = {"p208a1": range(2004, 2008), "p210": range(2004, 2010), "p211": range(2007, 2013), "ticuest01": [2016]}
for column, years in checks.items():
    print("\n", column)
    for year in years:
        try:
            f = enaho.load(year, "02", download_if_missing=False, columns=[column])
        except Exception as exc:
            print(year, "ABSENT", type(exc).__name__)
            continue
        if column not in f.columns:
            print(year, "ABSENT_COLUMN")
            continue
        v = pd.to_numeric(f[column], errors="coerce")
        print(year, v.value_counts(dropna=False).to_dict(), dictionary.value_labels(column, year, "02"))


