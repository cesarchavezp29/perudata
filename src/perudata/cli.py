"""
Command-line interface:  perudata <survey> [options]

    perudata enaho --years 2023 2024 --modules 01 34
    perudata panel --releases 2011 2023
    perudata endes --years 2024
    perudata epen --search "dpto 2024"
    perudata epen --codes 997 998
    perudata eea --year 2024
    perudata validate --years 2024
"""
from __future__ import annotations

import argparse

from . import eea, enaho, endes, epen, panel, validate


def main() -> None:
    ap = argparse.ArgumentParser(prog="perudata",
                                 description="Download Peru's INEI microdata")
    ap.add_argument("--out", default=None, help="data root (default ./peru_raw)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("enaho", help="ENAHO annual household survey")
    p.add_argument("--years", nargs="+", type=int, required=True)
    p.add_argument("--modules", nargs="+", default=None)
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("panel", help="ENAHO Panel (longitudinal)")
    p.add_argument("--releases", nargs="+", type=int, required=True)
    p.add_argument("--modules", nargs="+", default=None)
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("endes", help="ENDES (DHS) demographic & health survey")
    p.add_argument("--years", nargs="+", type=int, required=True)
    p.add_argument("--modules", nargs="+", default=None)
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("epen", help="EPE/EPEN employment surveys")
    p.add_argument("--codes", nargs="+", type=int, default=None)
    p.add_argument("--search", default=None)
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("eea", help="EEA annual economic survey (firms)")
    p.add_argument("--year", type=int, default=None)
    p.add_argument("--codes", nargs="+", default=None)
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("validate", help="reproduce official national poverty")
    p.add_argument("--years", nargs="+", type=int, default=None)

    a = ap.parse_args()
    if a.cmd == "enaho":
        enaho.download(a.years, a.modules, out=a.out, force=a.force)
    elif a.cmd == "panel":
        panel.download(a.releases, a.modules, out=a.out, force=a.force)
    elif a.cmd == "endes":
        endes.download(a.years, a.modules, out=a.out, force=a.force)
    elif a.cmd == "epen":
        if a.search:
            print(epen.search(a.search).to_string(index=False))
        elif a.codes:
            epen.download(a.codes, out=a.out, force=a.force)
        else:
            print(epen.catalog().to_string(index=False))
    elif a.cmd == "eea":
        if a.year:
            eea.download_year(a.year, out=a.out, force=a.force)
        elif a.codes:
            eea.download(a.codes, out=a.out, force=a.force)
        else:
            print(eea.catalog().to_string(index=False))
    elif a.cmd == "validate":
        validate.poverty(years=a.years, out=a.out)


if __name__ == "__main__":
    main()
