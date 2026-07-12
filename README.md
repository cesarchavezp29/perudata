# perudata

**Peru's official INEI microdata, one import away.**

```python
from perudata import enaho, validate

df = enaho.load(2024, "34")        # ENAHO sumaria: income, spending, poverty
validate.poverty(years=[2024])     # reproduces INEI's official 27.6% from raw data
```

Five national surveys, one consistent API. Every file is verified on download
by actually opening it, and a built-in validation gate reproduces INEI's
official poverty series **for all 22 years, 2004–2025, at the precision INEI
publishes it** (one decimal) before you build anything on top. The unrounded
residual never exceeds **0.05pp** — that is the rounding of the published
figure, not a disagreement, and the gate prints it rather than hiding it behind
a rounded zero.

| Survey | What it is | Coverage | Format |
|---|---|---|---|
| `enaho` | ENAHO — national household survey (income, poverty, employment, education, health, governance) | 2004–2025, 29 modules | Stata |
| `panel` | ENAHO Panel — same households re-interviewed (true poverty dynamics, FE) | 10 releases, 2007–2023 | Stata |
| `endes` | ENDES — Peru's DHS (fertility, child health, anemia, domestic violence) | 1996–2024 | SPSS |
| `epen` | EPE/EPEN — permanent employment surveys (Lima monthly since 2001, national) | 279 verified datasets | CSV |
| `eea` | EEA — annual economic survey of firms (sales, assets, employment, CIIU) | 2001–2024, 604 datasets | CSV |

## Install

```bash
pip install perudata            # once published; for now:
pip install git+https://github.com/cesarchavezp29/perudata
```

Requires Python ≥ 3.9. Dependencies: `pandas`, `pyreadstat`.

## Quickstart

```python
from perudata import enaho, endes, epen, eea, panel, validate

# --- ENAHO (annual cross-section) ------------------------------------------
enaho.years()                        # [2004, ..., 2025]
enaho.modules()                      # DataFrame of the 29 modules
enaho.download([2023, 2024], ["01", "34", "85"])
df = enaho.load(2024, "34")          # auto-downloads if missing

# national poverty, the official INEI way (person = factor07 x mieperho):
w = df["factor07"] * df["mieperho"]
poverty = 100 * w[df["pobreza"].isin([1, 2])].sum() / w.sum()   # -> 27.6

# --- validation gate ---------------------------------------------------------
validate.poverty()                   # full 2004-2025 table vs official INEI

# --- ENAHO Panel (longitudinal) ----------------------------------------------
panel.releases()                              # [2011, 2015, ..., 2022, 2023] — 10 releases
df, meta = panel.load_long(2023, "sumaria")   # latest: 2019-2023, tidy long
meta["waves"]                                 # [2019, 2020, 2021, 2022, 2023]
# any release works the same, e.g. the earliest 5-year panel:
df, meta = panel.load_long(2011, "sumaria")   # 2007-2011

# --- ENDES (DHS) --------------------------------------------------------------
endes.download(2024, ["peso_talla_anemia"])
kids = endes.load(2024, "peso_talla_anemia")

# --- EPEN (employment) ---------------------------------------------------------
epen.search("lima")                  # find datasets in the verified catalog
df = epen.load(997)                  # download + read by catalog code

# --- EEA (firms) ----------------------------------------------------------------
eea.modules(2024)                    # sector modules of EEA 2024
df = eea.load(eea.modules(2024)["csv_code"].iloc[0])
```

Or from the command line:

```bash
perudata enaho --years 2024 --modules 01 34
perudata validate --years 2024
perudata epen --search "dpto 2024"
```

## Where files go

Everything lands under `./peru_raw` (override per call with `out=` or globally
with the `PERUDATA_DIR` environment variable), named so you always know what a
file is:

```
peru_raw/
  enaho/sumaria/enaho-2024-34.dta
  enaho_panel/2011_302/panel-2011-sumaria.dta
  endes/2024_968/1629_hogar/968-Modulo1629/*.sav
  epen/804_15_lima.../*.csv
  eea/987-Modulo1968/a2022_s04_fF2/*.csv
  */_manifest.csv          # what was downloaded, when, rows x cols
```

Downloads are **idempotent**: a file that exists and verified is skipped, so
you can re-run a script after adding years and only the new ones are fetched.

## Why this exists

INEI publishes superb microdata, but using it programmatically means knowing
a pile of undocumented conventions, all of which this package encodes:

- Each survey-year is a numbered *proyecto* (`1031-Modulo34.zip`), and the
  codes are **not chronological** — code 279 is 2010 while 280–285 are
  2004–2009. Every ENAHO code here was verified by reading the internal `año`
  variable of its file.
- ENAHO 2004–2011 ships **Stata 7 (v110)** files that pandas cannot read —
  `load()` falls back to pyreadstat transparently.
- Sumaria zips carry `-12`/`-12g` alternates that silently lack the poverty
  variables. The canonical file is selected for you.
- ENDES exists **only in SPSS** for the full 1996–2024 series, and its module
  numbers were renumbered in 2020 (64–74 → 1629–1641).
- The ENAHO Panel changed module numbering in 2018 (01/34 → 1474–1479) and old
  releases are WIDE files; `panel.load_long()` returns a tidy long panel
  either way.
- EPEN and EEA are CSV-only with no year→code formula at all — the package
  ships verified catalogs (279 and 604 datasets) discovered by probing the
  server and opening every file.

## Validation

`validate.poverty()` recomputes national monetary poverty from the raw sumaria
(person-weighted, `factor07 × mieperho`, `pobreza ∈ {1,2}`) and compares it to
the official series from INEI's *Evolución de la Pobreza Monetaria* reports:

```
year  poverty_pct  official_poverty  pov_diff  poverty_exact  pov_diff_exact
2004         58.7              58.7       0.0        58.6990          -0.001
...
2024         27.6              27.6       0.0        27.5795          -0.021
2025         25.7              25.7       0.0        25.6667          -0.033
```

22/22 years match the published figure at INEI's own precision. `poverty_exact`
is the unrounded value and `pov_diff_exact` the unrounded residual (largest:
0.049pp, in 2006) — reported on purpose, because rounding our own number before
comparing would turn a real 0.03pp residual into a reported 0.0 and let the gate
flatter itself.

## Notes

- Data © INEI (Instituto Nacional de Estadística e Informática del Perú),
  published as open microdata. This package only automates download and
  reading — cite INEI and the survey when you publish.
- Value labels are not applied on load; you get the raw codes exactly as INEI
  documents them (the PDFs inside each zip are kept for EPEN/EEA).
- New ENAHO year out? `enaho.discover(2026)` scans the server for its code.

## License

MIT — see [LICENSE](LICENSE). Built by [Carlos Chávez Padilla](https://github.com/cesarchavezp29).
