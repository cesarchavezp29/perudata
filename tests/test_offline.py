"""Offline tests: catalogs, URL construction, module resolution, wide->long
reshape. No network needed."""
import io
import zipfile

import pandas as pd

from perudata import _core, eea, enaho, endes, epen, panel


def _zip_with_corrupt_member() -> bytes:
    """A zip whose PDF has a bad CRC but whose .dta is perfectly readable —
    exactly the shape of INEI's real 498-Modulo34.zip (ENAHO 2015)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Diccionario.pdf", b"P" * 200)
        z.writestr("sumaria-2015.dta", b"REALDATA" * 20)
    raw = bytearray(buf.getvalue())
    i = raw.find(b"P" * 200)          # scribble on the PDF payload -> CRC fails
    raw[i:i + 20] = b"\x00" * 20
    return bytes(raw)


def test_open_zip_tolerates_a_corrupt_member_we_do_not_need():
    """REGRESSION: a whole-archive testzip() gate rejected 498-Modulo34.zip
    because a documentation PDF had a bad CRC, so ENAHO 2015 sumaria was
    permanently undownloadable and validate.poverty() died for every user.
    The archive must open and the intact .dta must still be readable."""
    zf = _core.open_zip(_zip_with_corrupt_member())
    assert zf is not None, "archive rejected over a member we never extract"
    assert zf.read("sumaria-2015.dta") == b"REALDATA" * 20
    assert "Diccionario.pdf" in _core.bad_members(zf)


def test_open_zip_still_rejects_a_non_zip():
    """The throttle guard must survive: INEI answers bursts with an HTML error
    page under HTTP 200, and that must NOT be mistaken for an archive."""
    assert _core.open_zip(b"<html><body>error</body></html>") is None


def test_pick_main_dta_is_name_based_not_first_readable(tmp_path):
    """Now that the archive-level CRC gate is gone, member selection is the last
    thing standing between a tolerant extract and a readable-but-WRONG file.
    Sumaria zips ship -12/-12g variants that silently LACK the poverty vars, and
    the decoy here is deliberately the BIGGEST file, so a 'largest wins' or
    'first readable' rule would pick it. The canonical name must win."""
    decoy_big = tmp_path / "sumaria-2015-12g.dta"
    decoy_big.write_bytes(b"X" * 5000)            # biggest on purpose
    decoy = tmp_path / "sumaria-2015-12.dta"
    decoy.write_bytes(b"X" * 3000)
    real = tmp_path / "sumaria-2015.dta"
    real.write_bytes(b"X" * 100)                  # smallest on purpose
    picked = _core.pick_main_dta([decoy_big, decoy, real])
    assert picked == real, f"picked {picked.name}, a -12/-12g variant lacking pobreza"


def test_typed_failures_are_distinguishable():
    """Three failures used to wear one RuntimeError coat, which is what made
    ENAHO 2015 look like a throttle for three rounds. They must be tellable
    apart, and NotPublished must carry the URL it 404'd on."""
    assert issubclass(_core.NotPublished, _core.PerudataError)
    assert issubclass(_core.ServerRefused, _core.PerudataError)
    assert issubclass(_core.CorruptMember, _core.PerudataError)
    e = _core.NotPublished("https://x/302-Modulo02.zip")
    assert e.url.endswith("302-Modulo02.zip")
    assert not isinstance(e, _core.ServerRefused)


def test_panel_module_02_is_not_advertised():
    """REGRESSION: panel.OLD_MODULES listed module 02 by copying the ANNUAL map.
    INEI publishes no module 02 for ANY panel release (302-Modulo02.zip is a
    genuine 404). Advertising it made the package promise a file that does not
    exist. Verified against INEI's own `enahopanel` module catalogue."""
    for rel in panel.releases():
        assert "02" not in panel.modules_for(rel), f"release {rel} still offers M02"


def test_panel_roster_1314_only_exists_in_2016_2017():
    """The roster module IS real, but ONLY for releases 2016-2017 (old era).
    The 2011 and 2015 panels ship no roster at all — their person-level data
    lives in modules 03/04/05. Trimming 1314 outright would have deleted a
    true capability; year-gating it is the correct fix."""
    assert "1314" in panel.modules_for(2016)
    assert "1314" in panel.modules_for(2017)
    assert "1314" not in panel.modules_for(2011)
    assert "1314" not in panel.modules_for(2015)
    assert "1479" in panel.modules_for(2023)      # new-era roster still there


def test_enaho_years_and_urls():
    ys = enaho.years()
    assert ys[0] == 2004 and ys[-1] >= 2025
    assert enaho.url(2010, "34").endswith("/STATA/279-Modulo34.zip")
    assert enaho.url(2004, 34).endswith("/STATA/280-Modulo34.zip")
    assert len(enaho.modules()) == 29


def test_panel_module_resolution():
    assert panel.resolve_module(2011, "sumaria") == "34"
    assert panel.resolve_module(2023, "sumaria") == "1478"
    assert panel.url(2011, "34").endswith("/302-Modulo34.zip")


def test_endes_eras():
    assert 74 in endes.modules_for(2019)
    assert 1638 in endes.modules_for(2024)
    assert endes.resolve_module(2024, "peso_talla_anemia") == 1638
    assert endes.resolve_module(2015, "peso_talla_anemia") == 74
    assert "/SPSS/968-Modulo1638.zip" in endes.url(2024, "peso_talla_anemia")


def test_epen_catalog():
    cat = epen.catalog()
    assert len(cat) > 250
    assert {"code", "module", "label"} <= set(cat.columns)
    assert len(epen.search("lima")) > 0


def test_scalar_module_accepted():
    """download(year, 34) — a bare int/str module — must not raise. The scalar
    is coerced to a one-element list before iteration (regression guard)."""
    import inspect
    for mod in (enaho, endes, panel):
        src = inspect.getsource(mod.download)
        assert "isinstance(modules_, (int, str))" in src, mod.__name__


def test_eea_search_by_year():
    """Newer EEA labels drop the year ('Comercio F2' for 2023); search must
    still find them by matching the catalog's year column."""
    assert len(eea.search("2023")) > 0
    assert len(eea.search("comercio 2023")) > 0


def test_eea_catalog():
    cat = eea.catalog()
    assert len(cat) > 500
    assert 2024 in eea.years()
    assert len(eea.modules(2024)) > 0


def test_panel_wide_to_long():
    wide = pd.DataFrame({
        "cong": [1, 2], "vivi": [10, 20], "num_hog": [1, 1],
        **{f"pobreza_{y:02d}": [1, 2] for y in range(7, 12)},
        **{f"gashog2d_{y:02d}": [100.0, 200.0] for y in range(7, 12)},
        **{f"extra_{y:02d}": [0, 1] for y in range(7, 12)},
    })
    assert panel.detect_layout(list(wide.columns)) == "wide"
    long = panel.reshape_wide_to_long(wide)
    assert set(long["anio"]) == {2007, 2008, 2009, 2010, 2011}
    assert len(long) == 10
    assert {"pobreza", "gashog2d", "cong"} <= set(long.columns)


def test_panel_wide_to_long_suffixed_anchor():
    """Real panels ship the anchor id BOTH unsuffixed and year-suffixed
    (conglome + conglome_19..._23). The suffixed copies must not be renamed
    onto the anchor — that made two identical columns and crashed concat with
    'Reindexing only valid with uniquely valued Index objects' (regression)."""
    wide = pd.DataFrame({
        "conglome": [1, 2], "vivienda": [10, 20],
        **{f"conglome_{y:02d}": [1, 2] for y in range(19, 24)},
        **{f"vivienda_{y:02d}": [10, 20] for y in range(19, 24)},
        **{f"pobreza_{y:02d}": [1, 2] for y in range(19, 24)},
    })
    long = panel.reshape_wide_to_long(wide)          # must not raise
    assert set(long["anio"]) == {2019, 2020, 2021, 2022, 2023}
    assert len(long) == 10
    assert list(long.columns).count("conglome") == 1
    assert "pobreza" in long.columns
