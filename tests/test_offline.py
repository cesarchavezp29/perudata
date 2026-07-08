"""Offline tests: catalogs, URL construction, module resolution, wide->long
reshape. No network needed."""
import pandas as pd

from perudata import eea, enaho, endes, epen, panel


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
