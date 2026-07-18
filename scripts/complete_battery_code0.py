"""Make code 0 = 'No marcado' COMPLETE across all years for proven batteries.

The battery fixes only rewrote crosswalk rows that already said 'Pase' -- rows
the resolver had created. But in the many years where INEI's own .dta natively
labels code 0 'pase', the resolver accepted it and wrote no override, so the
crosswalk has no row there. value_labels() then falls back to the .dta 'pase',
and a researcher pooling 2004-2025 sees the SAME battery slot read 'pase' in
early years and 'No marcado' in later ones -- the one-code-one-meaning violation
harmonizing exists to remove (e.g. p314b1_8: 'pase' in 2019, 'No marcado' from
2021).

For every column the crosswalk already certifies as code 0 = 'No marcado' (a
battery proven administered by the admin0 test), this writes a 'No marcado'
override for every OTHER year where value_labels still leaks 'pase' from the
.dta. It only ever converts a 'pase'/absent code 0 to the label the same column
already carries elsewhere; it invents nothing and touches no other code.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import pandas as pd  # noqa: E402

from perudata import dictionary as dic  # noqa: E402

XW = Path(__file__).parents[1] / "src" / "perudata" / "crosswalks" / \
    "enaho_label_overrides.csv"

EVID = (
    "COMPLETES THE BATTERY ACROSS YEARS. This column's code 0 is certified 'No "
    "marcado' in other years by the administered-battery proof (a sibling flag "
    "== 1 co-occurring with a 0 in the released records). INEI's own .dta labels "
    "code 0 'pase' here, but that is the same exhaustive multiple-response "
    "battery, so code 0 means 'asked and not selected' in this year too. Written "
    "so the label is identical in every year -- one code, one meaning."
)


def main() -> int:
    o = pd.read_csv(XW, encoding="utf-8-sig", dtype=str)
    battery_cols = (o[(o.code == "0") & (o.label == "No marcado")]
                    [["module", "column"]].drop_duplicates())

    have = set(zip(o.module, o.column, o.year, o.code))
    new = []
    for r in battery_cols.itertuples(index=False):
        for y in range(2004, 2026):
            vl = dic.value_labels(r.column, y, r.module)
            c0 = vl.get("0")
            # any code-0 label INEI documents that is NOT already 'No marcado'
            # is a skip-marker variant ('pase', '[salto]', 'no aplica', ...)
            # leaking through where the crosswalk is incomplete; on a proven
            # administered battery, code 0 is 'No marcado' in every year.
            if c0 and c0.strip().lower() != "no marcado":
                key = (r.module, r.column, str(y), "0")
                if key not in have:
                    new.append({"module": r.module, "column": r.column,
                                "year": str(y), "code": "0",
                                "label": "No marcado", "status": "verified",
                                "evidence": EVID})
                    have.add(key)

    print(f"battery columns: {len(battery_cols)}")
    print(f"code-0 'No marcado' rows to add (years leaking a skip-marker): {len(new)}")
    if not new:
        print("nothing to complete")
        return 0

    # also UPDATE existing code-0 rows on these battery columns that still carry
    # a skip-marker ('No aplica', 'Pase') -- e.g. p20001c 2004 'No aplica'. The
    # spurious lone columns (p513, p4199) were reverted out of battery_cols, so
    # every column here is a coherent multi-slot battery where code 0 is
    # 'No marcado' in every year it exists.
    batset = set(zip(battery_cols.module, battery_cols.column))
    in_bat = pd.Series(
        [(m, c) in batset for m, c in zip(o.module, o.column)], index=o.index)
    upd = (o.code == "0") & (o.label != "No marcado") & in_bat
    n_upd = int(upd.sum())
    o.loc[upd, "label"] = "No marcado"
    o.loc[upd, "evidence"] = EVID
    print(f"updated {n_upd} existing skip-marker rows on battery cols -> No marcado")

    out = pd.concat([o, pd.DataFrame(new)], ignore_index=True)
    out.to_csv(XW, index=False, encoding="utf-8")

    # verify: no battery column leaks 'pase' any more
    dic._OVERRIDES = None                       # bust the cache
    leaks = 0
    for r in battery_cols.itertuples(index=False):
        for y in range(2004, 2026):
            c0 = dic.value_labels(r.column, y, r.module).get("0")
            if c0 and c0.strip().lower() != "no marcado":
                leaks += 1
    print(f"added {len(new)} rows; remaining skip-marker leaks on battery cols: {leaks}")
    assert leaks == 0, "some battery columns still leak a skip-marker at code 0"
    return 0


if __name__ == "__main__":
    sys.exit(main())
