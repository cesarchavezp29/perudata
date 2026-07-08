"""CI probe: is there an ENAHO proyecto code newer than the ones we map?

Scans a window above the highest known code for a live Modulo34 zip. On a hit
it opens a GitHub issue (once — skips codes already reported) so a maintainer
can content-verify the internal `año` and add one line to enaho.YEAR_CODE.
"""
from __future__ import annotations

import json
import subprocess

from perudata import enaho

WINDOW = 120


def existing_issue_codes() -> set[int]:
    try:
        out = subprocess.run(
            ["gh", "issue", "list", "--label", "new-inei-year", "--state", "all",
             "--json", "title"], capture_output=True, text=True, check=True).stdout
        codes = set()
        for it in json.loads(out or "[]"):
            for tok in it["title"].split():
                if tok.isdigit():
                    codes.add(int(tok))
        return codes
    except Exception:
        return set()


def main() -> None:
    top = max(enaho.YEAR_CODE.values())
    print(f"probing codes {top + 1}..{top + WINDOW} (newest mapped: "
          f"{enaho.latest_year()} = {top})")
    hits = enaho.discover(0, lo=top + 1, hi=top + WINDOW)
    if not hits:
        print("no new codes on the INEI server")
        return
    known = existing_issue_codes()
    fresh = [c for c in hits if c not in known]
    if not fresh:
        print(f"codes {hits} already reported")
        return
    body = (
        f"The INEI server answers 200 for Modulo34 at proyecto code(s) **{fresh}** — "
        f"likely ENAHO {enaho.latest_year() + 1}.\n\n"
        "Next steps:\n"
        "1. download it and read the internal `año` variable (codes are NOT chronological)\n"
        "2. add the verified line to `enaho.YEAR_CODE`\n"
        "3. run `perudata validate` for the new year against INEI's published poverty\n"
    )
    subprocess.run(
        ["gh", "issue", "create",
         "--title", f"New ENAHO proyecto code(s) live: {' '.join(map(str, fresh))}",
         "--label", "new-inei-year", "--body", body],
        check=True)
    print(f"issue created for {fresh}")


if __name__ == "__main__":
    main()
