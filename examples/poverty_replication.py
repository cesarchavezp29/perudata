"""
Reproduce INEI's official national poverty series from raw ENAHO microdata.

Downloads the sumaria (module 34) for the requested years into ./peru_raw and
prints computed vs official poverty. Expect 0.0pp differences.

    python examples/poverty_replication.py 2022 2023 2024
"""
import sys

from perudata import validate

years = [int(y) for y in sys.argv[1:]] or [2023, 2024, 2025]
validate.poverty(years=years)
