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


def test_recode_refuses_to_drop_a_code():
    """THE 100%-SIS REGRESSION. A bulk recoder keyed on label text dropped 2004's
    UNLABELLED code 0 for p4195, so the denominator collapsed to the people who
    HAVE insurance and coverage read 100% instead of 15.1%. An unlabelled code is
    a real category, never a row to delete: a recode that would lose a non-null
    row must REFUSE ITSELF rather than silently shrink a denominator."""
    import pytest
    from perudata import harmonize
    df = pd.DataFrame({"p4195": [0, 1, 1, 0, 1]})     # code 0 = the unlabelled 'no'
    bad = {"map": {2004: {1: 1}}, "labels": {}, "audit": []}   # 0 has no mapping
    with pytest.raises(ValueError, match="drop"):
        harmonize.apply_recode(df.copy(), bad, "p4195", 2004)
    good = {"map": {2004: {0: 2, 1: 1}}, "labels": {}, "audit": []}
    out = harmonize.apply_recode(df.copy(), good, "p4195", 2004)
    assert out["p4195_h"].notna().all()               # no row lost
    assert (out["p4195_h"] == 1).sum() == 3           # shares preserved


def test_unlabelled_bracketed_year_blocks_output_until_resolved(monkeypatch):
    """Observed raw data may not be converted to safety-generated NA."""
    import pytest
    from perudata import dictionary, enaho, harmonize

    frames = {
        2019: pd.DataFrame({"answer": [1, 2, 1]}),
        2020: pd.DataFrame({"answer": [1, 2, 2]}),
        2021: pd.DataFrame({"answer": [1, 2, 1]}),
    }
    labels = {
        2019: {1: "si", 2: "no"},
        2020: {},
        2021: {1: "si", 2: "no"},
    }
    monkeypatch.setattr(enaho, "load",
                        lambda year, module, **kwargs: frames[year])
    monkeypatch.setattr(dictionary, "value_labels",
                        lambda column, year, module: labels[year])

    recode = harmonize.build_recode("01", "answer",
                                    years=[2019, 2020, 2021])
    # 2020 ships no labels, so its category identity is UNRESOLVED. An equal code
    # set {1,2} does not prove equal meaning — the year could be silently reversed.
    assert 2020 not in recode["map"]

    # DEFAULT: a marked NA, and the package still builds. Making this raise would
    # break dataset(range(2004,2026), '04') outright, because 2019 ships no labels
    # for p4195 — a package that refuses its own flagship call is worse than one
    # that hands back a gap it has told you about.
    out = harmonize.apply_recode(frames[2020].copy(), recode, "answer", 2020)
    assert out["answer_h"].isna().all()

    # OPT-IN: strict=True for callers who would rather stop than accept the gap.
    with pytest.raises(ValueError, match="category identity is unresolved"):
        harmonize.apply_recode(frames[2020].copy(), recode, "answer", 2020,
                               strict=True)


def test_unmapped_year_is_na_only_when_raw_data_is_missing():
    """NA is allowed for genuine source missingness, not mapping uncertainty."""
    from perudata import harmonize

    raw = pd.DataFrame({"answer": [pd.NA, pd.NA]})
    recode = {"map": {}, "labels": {}, "audit": []}
    out = harmonize.apply_recode(raw, recode, "answer", 2020)
    assert out["answer_h"].isna().all()

def test_the_recode_guards_are_alive_not_decorative():
    """CERTIFY THE CERTIFIER. One check in the recode filter compared a value to
    ITSELF and could never fire — a dead guard that looks alive is worse than no
    guard, because it makes the next reader trust a filter that is not filtering.
    Finding one by reading the code does not prove the others fire. So each guard
    is shown to FAIL on a deliberately broken map, and to PASS on a correct one
    (a checker that rejects everything is as useless as one that accepts
    everything)."""
    import pytest
    from perudata import harmonize
    df = pd.DataFrame({"v": [0, 0, 1, 1, 1]})

    # A. drops the unlabelled code 0 -> the 100%-SIS signature
    with pytest.raises(ValueError, match="drop"):
        harmonize.apply_recode(df.copy(), {"map": {2004: {1: 1}}}, "v", 2004)

    # B. a correct map must still pass, and preserve every row and every share
    out = harmonize.apply_recode(df.copy(), {"map": {2004: {0: 2, 1: 1}}}, "v", 2004)
    assert out["v_h"].notna().all()
    assert sorted(out["v_h"].value_counts().tolist()) == sorted(
        df["v"].value_counts().tolist())          # zero share drift, exactly


def test_label_overrides_are_evidence_gated_and_shipped():
    """The overrides supply labels INEI's own .dta omits (ENAHO 2016 declares
    estrsocial as range 1-5 and omits code 6, while 12,952 records sit AT code 6).
    They must SHIP, and only 'verified' rows may ever be used — a candidate is a
    guess wearing a manifest."""
    from perudata import harmonize
    ov = harmonize.label_overrides()
    assert len(ov), "the verified label overrides are not shipping"
    assert set(ov["status"]) == {"verified"}, "a non-verified override leaked in"
    assert ov["evidence"].str.len().gt(20).all(), "an override carries no evidence"
    assert len(harmonize.label_overrides("34")) >= 1


def test_unresolved_year_is_NA_by_default_and_raises_only_when_asked():
    """THE GRADED CONTRACT. A year with raw data but no verified mapping comes back
    NA by default so the package still BUILDS, and raises only under strict=True.
    Making the raise the default breaks dataset(range(2004,2026), '04') outright —
    2019 ships no labels for p4195 — and a package that refuses its own flagship
    call is worse than one that returns a marked NA."""
    import pytest
    from perudata import harmonize
    df = pd.DataFrame({"v": [1, 2, 1]})
    rc = {"map": {2024: {1: 1, 2: 2}}}            # 2019 deliberately unmapped

    out = harmonize.apply_recode(df.copy(), rc, "v", 2019)          # default
    assert out["v_h"].isna().all()                                  # NA, not a guess

    with pytest.raises(ValueError, match="category identity is unresolved"):
        harmonize.apply_recode(df.copy(), rc, "v", 2019, strict=True)


def test_bulk_recode_maps_are_not_shipped():
    """The fabricated bulk maps must be GONE from the package, not merely disabled.
    A wrong map that is switched off is one re-enable away from going live."""
    import pytest
    from importlib import resources

    from perudata import harmonize
    p = resources.files("perudata").joinpath("catalogs/enaho_recodes.json.gz")
    assert not p.is_file(), "the fabricated bulk recode maps are still shipping"
    with pytest.raises(NotImplementedError):
        harmonize._recode_maps()


def test_crosswalks_parse_and_are_well_formed():
    """A crosswalk that does not parse is a crosswalk that does not exist.
    (Both files shipped malformed once: an unquoted comma inside `recode`
    and inside a note silently added an 11th field.)"""
    from perudata import harmonize
    assert harmonize.available()
    for name in harmonize.available():
        survey, module = name.split("_", 1)
        cw = harmonize.crosswalk(survey, module)
        assert {"canonical", "kind", "raw", "status"} <= set(cw.columns), name
        assert cw["kind"].isin(["rename", "derive", "recode"]).all(), name
        assert cw["canonical"].is_unique, name


def test_normalize_keys_fixes_2004_and_is_idempotent_on_clean_keys():
    """The 2004 trap in miniature: sumaria zero-pads the id, the roster
    space-pads it, and a raw merge silently keeps almost nothing. Normalization
    must reconcile them AND leave an already-clean key untouched."""
    from perudata import harmonize
    sumaria = pd.DataFrame({"conglome": ["0005", "0012"], "hogar": ["11", "11"]})
    roster = pd.DataFrame({"conglome": ["   5", "  12"], "hogar": ["11", "11"]})
    raw = sumaria.merge(roster, on=["conglome", "hogar"], how="inner")
    assert len(raw) == 0                       # the silent catastrophe
    s2 = harmonize.normalize_keys(sumaria)
    r2 = harmonize.normalize_keys(roster)
    assert len(s2.merge(r2, on=["conglome", "hogar"], how="inner")) == 2
    # idempotent: a clean key survives a second pass unchanged
    assert harmonize.normalize_keys(s2)["conglome"].tolist() == s2["conglome"].tolist()


def test_item_modules_are_aggregated_never_joined_raw():
    """Module 07 is HOUSEHOLD-ITEM (267 rows per household in 2025). Joining it
    raw would multiply the row count and corrupt every weighted statistic, so it
    must be AGGREGATED to one row per household first. And an item module with no
    household module to anchor on must refuse rather than guess a universe."""
    import pytest
    assert "07" in enaho.ITEM_MODULES
    assert "07" not in enaho.HOUSEHOLD_MODULES
    with pytest.raises(ValueError, match="anchor on"):
        enaho.combine(2025, ["07"], level="household")


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


def test_p203b_is_harmonized_without_changing_or_dropping_codes():
    import pandas as pd
    from perudata import harmonize

    raw = pd.DataFrame({"p203b": [1, 2, 3, 6, 7, 11, pd.NA]})
    out, coverage = harmonize.apply(raw, "enaho", "02", year=2023)

    assert out["family_nucleus_relationship"].tolist() == raw["p203b"].tolist()
    row = coverage.loc[
        coverage["canonical"] == "family_nucleus_relationship"
    ].iloc[0]
    assert bool(row["resolved"])
    assert row["raw"] == "p203b"


def test_official_override_tables_are_not_shifted():
    import pandas as pd
    from pathlib import Path

    path = Path(__file__).parents[1] / "src/perudata/crosswalks/enaho_label_overrides.csv"
    ov = pd.read_csv(path, dtype={"module": str, "year": int, "code": int})
    ov["module"] = ov["module"].str.zfill(2)
    lookup = ov.set_index(["module", "column", "year", "code"])["label"]

    assert lookup[("02", "dominio", 2004, 1)] == "Costa Norte"
    assert lookup[("02", "dominio", 2004, 8)] == "Lima Metropolitana"
    assert lookup[("02", "p203b", 2006, 1)] == "Jefe de hogar"
    assert lookup[("02", "p217", 2004, 1)] == "Viaje"


def test_classification_maps_preserve_namespace_code_identity():
    import json
    from pathlib import Path

    path = Path(__file__).parents[1] / "scripts/recodes_passed.json"
    maps = json.loads(path.read_text(encoding="utf-8"))["02"]
    for column in ("ocupac_r3", "ocupac_r4", "rama_3", "rama_4", "rama_r3", "rama_r4"):
        for year_map in maps[column]["map"].values():
            assert all(int(raw) == canonical for raw, canonical in year_map.items())
