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
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
        if zf.testzip() is not None:
            return None
        return zf
    except zipfile.BadZipFile:
        return None


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
