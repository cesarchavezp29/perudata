"""
Shared plumbing for all perudata survey modules: HTTP with retries, zip
extraction, robust Stata/SPSS readers, data directory resolution and
per-survey download manifests.

All INEI microdata lives on one host, served as numbered "proyecto" zips:

    https://proyectos.inei.gob.pe/iinei/srienaho/descarga/{FORMAT}/{CODE}-Modulo{NN}.zip

Every survey module in this package resolves (year, module) -> CODE and
delegates the transport to the helpers here.
"""
from __future__ import annotations

import csv
import io
import os
import re
import shutil
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://proyectos.inei.gob.pe/iinei/srienaho/descarga"
UA = "Mozilla/5.0 (perudata; https://github.com/cesarchavezp29/perudata)"


# --------------------------------------------------------------------------- #
# typed failures
# --------------------------------------------------------------------------- #
# Three genuinely different things used to surface as one RuntimeError
# ("could not obtain X"), and that ambiguity cost real debugging: ENAHO 2015 was
# misread as a throttle three times when the archive was actually fine and OUR
# CRC gate was discarding it, and panel module 02 was nearly trimmed from the
# catalog when the real question was whether INEI publishes it at all.
#
# A user seeing a failure needs to know which of these it is, because the
# correct response differs: retry / report a bug / accept the file is not there.
class PerudataError(Exception):
    """Base for every failure this package raises."""


class NotPublished(PerudataError):
    """INEI has no such file: the constructed URL returned 404.

    Carries the URL so the caller can tell "the server says no such file" apart
    from "our catalog never listed it". When the catalog CLAIMS a module and the
    URL 404s, that disagreement is the signal to go check INEI's codebook rather
    than trust either side -- exactly the panel-02 case.
    """

    def __init__(self, url: str, msg: str = ""):
        self.url = url
        super().__init__(msg or f"INEI returned 404 for {url} (not published)")


class ServerRefused(PerudataError):
    """The host refused, timed out, or answered a throttle page. TRANSIENT — retry."""

    def __init__(self, url: str, attempts: int, detail: str = ""):
        self.url, self.attempts = url, attempts
        super().__init__(
            f"INEI refused/timed out after {attempts} attempts: {url} "
            f"({detail or 'no usable response'}). Transient — retry later.")


class CorruptMember(PerudataError):
    """The archive downloaded and opened, but the DATA member is unreadable.

    Not transient and not a 404: retrying will not help and the file does exist.
    A damaged AUXILIARY member (a PDF) is NOT this error — those are tolerated,
    since we never extract them.
    """

    def __init__(self, url: str, member: str, detail: str = ""):
        self.url, self.member = url, member
        super().__init__(
            f"data member {member!r} in {url} is corrupt ({detail}). "
            f"The file exists but its data is damaged upstream — report to INEI.")


# --------------------------------------------------------------------------- #
# data directory
# --------------------------------------------------------------------------- #
def data_dir(out: str | Path | None = None) -> Path:
    """Resolve the root folder for raw downloads.

    Priority: explicit `out` argument > PERUDATA_DIR env var > ./peru_raw
    """
    root = Path(out) if out else Path(os.environ.get("PERUDATA_DIR", "peru_raw"))
    root.mkdir(parents=True, exist_ok=True)
    return root


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
# INEI's TLS chain fails default verification from some networks (observed on
# GitHub-hosted runners; the same host works fine with relaxed verification).
# First attempt verifies normally, later attempts fall back to an unverified
# context -- we only READ public zips from this host, integrity is checked by
# opening every file after download.
def _relaxed_ctx():
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def get(url: str, timeout: int = 300, tries: int = 5) -> bytes | None:
    """GET with backoff on throttling, no retry on a genuine 404."""
    for i in range(tries):
        try:
            ctx = None if i == 0 else _relaxed_ctx()
            with urlopen(Request(url, headers={"User-Agent": UA}),
                         timeout=timeout, context=ctx) as r:
                if r.status == 200:
                    return r.read()
        except HTTPError as e:
            if e.code == 404:
                return None
        except (URLError, TimeoutError, OSError):
            pass
        time.sleep(5 * (i + 1))
    return None


def fetch(url: str, timeout: int = 300, tries: int = 5) -> bytes:
    """Typed GET: bytes on success, NotPublished on 404, ServerRefused otherwise.

    This is get() with the failure reason preserved instead of collapsed to None.
    """
    detail = ""
    for i in range(tries):
        try:
            ctx = None if i == 0 else _relaxed_ctx()
            with urlopen(Request(url, headers={"User-Agent": UA}),
                         timeout=timeout, context=ctx) as r:
                if r.status == 200:
                    return r.read()
                detail = f"HTTP {r.status}"
        except HTTPError as e:
            if e.code == 404:
                raise NotPublished(url) from None   # definitive: do not retry
            detail = f"HTTP {e.code}"
        except (URLError, TimeoutError, OSError) as e:
            detail = f"{type(e).__name__}: {e}"
        time.sleep(5 * (i + 1))
    raise ServerRefused(url, tries, detail)


def head_ok(url: str, timeout: int = 15) -> bool:
    try:
        req = Request(url, headers={"User-Agent": UA}, method="HEAD")
        with urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except (HTTPError, URLError, TimeoutError, OSError):
        return False


# --------------------------------------------------------------------------- #
# readers (version-proof)
# --------------------------------------------------------------------------- #
def read_dta(path: str | Path, columns: list[str] | None = None):
    """Read a Stata file of ANY vintage.

    pandas rejects Stata 7 (format 110) files, which INEI still ships for
    ENAHO 2004-2011. pyreadstat handles those, so we fall back to it.
    Value labels are NOT applied (you get the raw codes, as INEI documents them).
    """
    import pandas as pd
    try:
        return pd.read_stata(path, convert_categoricals=False, columns=columns)
    except ValueError:
        import pyreadstat
        df, _ = pyreadstat.read_dta(str(path), usecols=columns,
                                    disable_datetime_conversion=True)
        return df


def read_sav(path: str | Path, columns: list[str] | None = None):
    """Read an SPSS .sav file (ENDES ships SPSS for every year)."""
    import pyreadstat
    df, _ = pyreadstat.read_sav(str(path), usecols=columns)
    return df


def verify_dta(path: Path) -> tuple[bool, int, int]:
    """Open the .dta and return (ok, n_rows, n_cols) without trusting byte size."""
    try:
        df = read_dta(path)
        return (len(df) > 0 and df.shape[1] > 0), int(len(df)), int(df.shape[1])
    except Exception:
        return False, 0, 0


def verify_sav(path: Path) -> tuple[bool, int, int]:
    try:
        import pyreadstat
        _, m = pyreadstat.read_sav(str(path), metadataonly=True)
        return m.number_rows > 0, m.number_rows, m.number_columns
    except Exception:
        return False, 0, 0


def csv_shape(path: Path) -> tuple[int, int]:
    """Cheap (rows, cols) for a CSV without loading it into memory."""
    try:
        with open(path, "r", encoding="latin-1", errors="replace", newline="") as f:
            rd = csv.reader(f)
            header = next(rd, [])
            return sum(1 for _ in rd), len(header)
    except Exception:
        return 0, 0


# --------------------------------------------------------------------------- #
# zip handling
# --------------------------------------------------------------------------- #
def open_zip(blob: bytes) -> zipfile.ZipFile | None:
    """Open an INEI zip, tolerating a corrupt member we do not need.

    A whole-archive testzip() gate is WRONG here. ENAHO 2015 (498-Modulo34.zip)
    ships a documentation PDF with a bad CRC while sumaria-2015.dta inside the
    SAME archive reads perfectly. Failing the archive threw away the data file
    and made 2015 permanently undownloadable -- which in turn killed
    validate.poverty() for every user, since the gate needs every year.

    Integrity is not weakened: every member we actually extract is opened and
    verified afterwards (verify_dta / verify_sav / csv_shape), and a CRC-bad
    data member still raises on extract and is skipped by extract_members().
    A throttled HTML error page served as a "zip" is still rejected here,
    because it is not a zip at all and raises BadZipFile.
    """
    try:
        return zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        return None


def bad_members(zf: zipfile.ZipFile) -> list[str]:
    """Names of members that fail their CRC check (diagnostic only)."""
    try:
        first = zf.testzip()
    except Exception:
        return []
    return [first] if first else []


def fetch_zip(url: str, tries: int = 3, cooldown: int = 35, pace: float = 2.0
              ) -> zipfile.ZipFile:
    """Download and open an INEI zip, with typed failures.

    Raises NotPublished (404), ServerRefused (throttle/timeout/refusal).
    INEI throttles bursts by answering an HTML error page under HTTP 200 — that
    is not a zip, so open_zip() rejects it and we cool down and retry. A zip that
    opens is returned even if an AUXILIARY member is CRC-damaged (see open_zip).
    """
    detail = ""
    for attempt in range(tries):
        if attempt:
            time.sleep(cooldown)          # throttled: let the host cool off
        blob = fetch(url)                 # NotPublished propagates immediately
        zf = open_zip(blob)
        if zf is not None:
            time.sleep(pace)              # pacing keeps the throttle asleep
            return zf
        detail = "response was not a zip (throttle page?)"
    raise ServerRefused(url, tries, detail)


def extract_members(zf: zipfile.ZipFile, dest: Path, suffixes: tuple[str, ...]) -> list[Path]:
    """Extract only members with the given suffixes (INEI zips carry PDFs with
    non-ASCII names that can break a blanket extractall)."""
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for m in zf.namelist():
        if m.lower().endswith(suffixes):
            try:
                zf.extract(m, dest)
                out.append(dest / m)
            except Exception:
                continue
    return out


def pick_main_dta(paths: list[Path]) -> Path | None:
    """Pick the canonical .dta among alternates.

    Sumaria zips ship '-12'/'-12g' groupings that LACK analysis variables
    (e.g. pobreza). Prefer the canonical file, then the largest.
    """
    dtas = [p for p in paths if p.suffix.lower() == ".dta"]
    if not dtas:
        return None
    exact = [p for p in dtas if re.fullmatch(r"sumaria-\d{4}\.dta", p.name.lower())]
    if exact:
        return max(exact, key=lambda p: p.stat().st_size)
    pool = [p for p in dtas if not re.search(r"-12g?\.dta$", p.name.lower())] or dtas
    return max(pool, key=lambda p: p.stat().st_size)


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #
MANIFEST_COLS = ["survey", "year", "module", "code", "file", "n_rows", "n_cols",
                 "bytes", "downloaded_utc"]


def manifest_append(root: Path, row: dict) -> None:
    """Append one download record to <root>/_manifest.csv (idempotent per file)."""
    mpath = root / "_manifest.csv"
    rows: dict[str, dict] = {}
    if mpath.exists():
        with open(mpath, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows[r["file"]] = r
    row = {c: str(row.get(c, "")) for c in MANIFEST_COLS}
    row["downloaded_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows[row["file"]] = row
    with open(mpath, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_COLS)
        w.writeheader()
        for _, r in sorted(rows.items()):
            w.writerow(r)


def rmtree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def clean_columns(df):
    """Lower-case column names and strip BOM artifacts (﻿, mojibake)."""
    df.columns = [c.lower().replace("﻿", "").replace("ï»¿", "").strip()
                  for c in df.columns]
    return df
