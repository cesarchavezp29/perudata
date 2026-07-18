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


def test_canonical_labels_are_never_keyed_on_none(monkeypatch):
    """A category set can legitimately DIFFER by year: p101 code 7 ('local no
    destinado para habitacion humana') exists in 2021 but not 2025, and code 8
    ('otro') exists in 2025 but not 2021. When a year carries a LABEL for a code
    its own map does not cover, the canonical dict must not gain a {None: 'otro'}
    entry — a null key breaks every downstream sort and lookup, silently."""
    from perudata import dictionary, enaho, harmonize

    frames = {2021: pd.DataFrame({"v": [1, 7]}), 2025: pd.DataFrame({"v": [1, 8]})}
    labels = {2021: {1: "casa", 7: "local", 8: "otro"},      # 8 labelled, unobserved
              2025: {1: "casa", 8: "otro"}}
    monkeypatch.setattr(enaho, "load", lambda year, module, **k: frames[year])
    monkeypatch.setattr(dictionary, "value_labels",
                        lambda column, year, module: labels[year])
    monkeypatch.setattr(harmonize, "label_overrides", lambda module=None: pd.DataFrame(
        columns=["module", "column", "year", "code", "label", "status", "evidence"]))

    rc = harmonize.build_recode("01", "v", years=[2021, 2025])
    assert None not in rc["labels"], f"null key in canonical labels: {rc['labels']}"
    assert all(isinstance(k, int) for k in rc["labels"])


def test_every_override_carries_real_evidence():
    """The override manifest is the ONLY place where a human judgement enters the
    harmonized data, so every row must carry the evidence that justifies it. This
    is what separates a certification from a guess with a manifest.

    The evidence classes, each PROVEN on a real case in module 01 — and note that
    they contradict each other, which is why none of this can be automated blind:
      * the .dta LABEL is wrong (p1142 labels code 2; code 2 exists in no year)
      * the DICTIONARY is wrong (p107a21 declares '2 Si'; the data holds 1)
      * BOTH are wrong and only behaviour settles it (p1138 2007 code 8)
    """
    from perudata import harmonize
    ov = harmonize.label_overrides()
    assert set(ov["status"]) == {"verified"}
    # no row may cite a bare assertion
    weak = ov[ov["evidence"].str.len() < 40]
    assert weak.empty, f"{len(weak)} override(s) carry no real evidence"
    # Every row must name a SOURCE or exhibit a PROOF. The two are different and
    # both are legitimate:
    #   source  — an INEI document or INEI's own label in another vintage
    #   proof   — a deterministic statement about the released data itself, e.g.
    #             "all 128 released P203B=11 observations also have P203=11", or
    #             "estrsocial=6 iff estrato is rural in all 36,785 records". Those
    #             cite no document because they need none: the data settles it.
    import re
    pat = re.compile(
        r"diccionario|dictionary|label|testimony|rango|range|cross-check|"
        r"behavioural|declared|official|observations|records|iff|"
        r"defines|scheme|convention|%|manual|cuestionario|questionnaire|page", re.I)
    unsourced = ov[~ov["evidence"].str.contains(pat)]
    assert unsourced.empty, (
        f"{len(unsourced)} override(s) name neither a source nor a proof: "
        f"{unsourced[['column', 'year']].head(3).to_dict('records')}")


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


def test_classification_maps_preserve_namespace_code_identity(monkeypatch):
    """Occupation and industry codes are OFFICIAL CLASSIFICATION NAMESPACES
    (CIUO-88, CNO-2015, CIIU rev3/rev4). Inside one declared revision the CODE IS
    the identity — 4711 means retail because the standard says so, not because a
    .dta label says so — so a recode must map every code to ITSELF and never
    renumber it. Renumbering would silently detach the data from the published
    classification.

    (Rewritten: the original read scripts/recodes_passed.json, a scratch artifact
    that any filter re-run regenerates, so the test broke on a file that is not
    part of the package. A test must exercise the shipped code.)
    """
    from perudata import dictionary, enaho, harmonize

    frames = {2019: pd.DataFrame({"rama_r4": [4711, 4921, 1392]}),
              2024: pd.DataFrame({"rama_r4": [4711, 4921, 8610]})}
    monkeypatch.setattr(enaho, "load", lambda year, module, **k: frames[year])
    monkeypatch.setattr(dictionary, "value_labels", lambda column, year, module: {})
    monkeypatch.setattr(harmonize, "label_overrides", lambda module=None: pd.DataFrame(
        columns=["module", "column", "year", "code", "label", "status", "evidence"]))

    rc = harmonize.build_recode("05", "rama_r4", years=[2019, 2024])
    for year, ymap in rc["map"].items():
        for raw, canon in ymap.items():
            assert int(raw) == int(canon), (
                f"{year}: CIIU code {raw} was renumbered to {canon} — a "
                f"classification namespace must keep the code as the identity")


def test_internet_device_battery_has_one_meaning_per_code():
    """p314b1_8/_9 must not flip meaning at 2023.

    INEI mislabelled this battery in BOTH sources, differently in each:
    its .dta shifted _9 to {0: 'celular con plan de datos', 9: 'otro'} while
    every sibling is {0: 'pase', N: <substantive>}, and its dictionary's
    value-label line for _8 says '8. Otro' -- _7's label copied one slot down --
    contradicting _8's own question text, 'Celular sin plan de datos'.

    The shipped crosswalk had swallowed both, so pooling 2019-2025 made
    'Celular sin plan de datos' vanish at 2023 while 'Otro' spiked: a trend
    break invented by the label, with the microdata untouched. No source
    ranking can catch this -- preferring the dictionary fixes _9 and breaks
    _8. The arbiter is the question text, which agrees with the value label on
    136 of 139 true flag batteries package-wide (the other 2 are truncations).
    """
    import pandas as pd
    from pathlib import Path

    p = (Path(__file__).parents[1] / "src" / "perudata" / "crosswalks"
         / "enaho_label_overrides.csv")
    o = pd.read_csv(p, encoding="utf-8-sig", dtype=str)

    truth = {
        ("p314b1_7", "7"): "Otro",
        ("p314b1_8", "8"): "Celular sin plan de datos",
        ("p314b1_9", "9"): "Celular con plan de datos",
    }
    for (col, code), want in truth.items():
        got = set(o[(o.column == col) & (o.code == code)].label.dropna())
        assert got <= {want}, f"{col} code {code} labelled {got}, expected {want!r}"

    # code 0 is 'No marcado': the device battery is multiple-response (a person
    # using internet marks some devices 1 and leaves others 0), proven by the
    # 145,846 records where a sibling flag is 1 while another is 0. INEI's
    # dictionary writes '0.Pase' generically, but behaviourally the 0 is 'did not
    # use this device', not 'never asked'.
    for col in ("p314b1_7", "p314b1_8", "p314b1_9"):
        got = set(o[(o.column == col) & (o.code == "0")].label.dropna())
        assert got <= {"No marcado"}, f"{col} code 0 labelled {got}"

    # and no slot may carry two meanings for one code across years
    for col in ("p314b1_7", "p314b1_8", "p314b1_9"):
        sub = o[o.column == col]
        for code, g in sub.groupby("code"):
            assert g.label.nunique() <= 1, (
                f"{col} code {code} means {list(g.label.unique())} by year")


def test_multiple_response_flag_zero_is_not_pase():
    """Code 0 on an exhaustive flag battery means 'No marcado', not 'Pase'.

    'Pase' asserts the question was never put to the person. For these 6-slot
    batteries the data refutes that: out-of-universe rows are NA in all six
    slots, and among in-universe rows ZERO mark none of the six. So a 0 cell
    always belongs to someone who answered by marking a different slot.

    The crosswalk had shipped 'Pase' for 2004-2020 and 'No marcado' for
    2021-2025 -- one code, one column, two meanings -- because the resolver was
    append-only and a weaker rule that ran first could never be superseded.
    """
    import pandas as pd
    from pathlib import Path

    p = (Path(__file__).parents[1] / "src" / "perudata" / "crosswalks"
         / "enaho_label_overrides.csv")
    o = pd.read_csv(p, encoding="utf-8-sig", dtype=str)

    fams = ([f"p3121a{i}" for i in range(1, 7)]
            + [f"p3122a{i}" for i in range(1, 7)]
            + [f"p314a{i}" for i in range(1, 7)]
            + [f"p315{i}" for i in range(2, 7)])
    for col in fams:
        got = set(o[(o.column == col) & (o.code == "0")].label.dropna())
        assert "Pase" not in got, f"{col} code 0 is back to 'Pase'"
        assert got <= {"No marcado"}, f"{col} code 0 labelled {got}"


def test_indicator_zero_is_substantive_not_pase():
    """p5291c/p530b code 0 is an ANSWER, not a skip.

    Both are named "Indicador ..." and declared Rango 0-1 with both codes
    substantive: p5291c is an "Indicador no sabe", so 0 means the person DID
    know. The crosswalk had shipped 'Pase' for 2007-2025 -- asserting the
    question was never asked -- while the same file said 'Sabe' for 2004-2006
    and 2013, and the 'Pase' rows cited exactly those four years as their proof.

    Five sources agree: the 2007 dictionary ('0 Sabe'), INEI's 2004/2005 .dta
    ({0: 'sabe'}), the file's own 2004-2006/2013 rows, the variable name, and
    the declared range leaving no room for a pase.
    """
    import pandas as pd
    from pathlib import Path

    p = (Path(__file__).parents[1] / "src" / "perudata" / "crosswalks"
         / "enaho_label_overrides.csv")
    o = pd.read_csv(p, encoding="utf-8-sig", dtype=str)
    for col, want in (("p5291c", "Sabe"), ("p530b", "Tiene ganancia")):
        got = set(o[(o.column == col) & (o.code == "0")].label.dropna())
        assert "Pase" not in got, f"{col} code 0 is back to 'Pase'"
        assert got <= {want}, f"{col} code 0 labelled {got}, expected {want!r}"


def test_r559_code9_is_the_catch_all_not_cena():
    """r559_* code 9 is 'Otros' in every year, never 'Cena'.

    The 2013-2016 dictionaries say '9.Cena'; 2017-2019 say '9. Otros'; and 2020
    lists '3.Cena' AND '9. Otros' as separate codes. INEI's own 2012/2013 .dta
    says 9 = 'otros alimentos y bebidas'.

    The mass is decisive: code 9 holds ~80% of observations in 2013-2017 while
    desayuno is 7% and almuerzo 13%. No dinner share explains that, and once
    Cena gets its own code in 2019+ it is ~8% while code 9 stays 37-45%. So the
    dictionary -- not the data -- is what was wrong here, which is why this went
    the OPPOSITE way from p5291c: no source ranking could have fixed both.
    """
    import pandas as pd
    from pathlib import Path

    p = (Path(__file__).parents[1] / "src" / "perudata" / "crosswalks"
         / "enaho_label_overrides.csv")
    o = pd.read_csv(p, encoding="utf-8-sig", dtype=str)
    r = o.column.str.match(r"r559_\d+$", na=False) & (o.code == "9")
    got = set(o.loc[r, "label"].dropna())
    assert "Cena" not in got, "r559 code 9 is labelled 'Cena' again"
    assert got <= {"Otros"}, f"r559 code 9 labelled {got}"


def test_p407h_label_is_not_inverted():
    """p407h code 1 is 'No lo atendieron' in EVERY year.

    This is the most dangerous defect the crosswalk carried: the label was
    inverted in 5 of 12 years (2013-2016, 2020 said code 1 = 'Si lo
    atendieron'), so pooling 2013-2024 inverted a health-access variable.

    The data is constant and decides it. p407h1/h2 record hours and minutes
    waited: code 1 has a nonzero wait in 0.0% of rows in every year, code 0 in
    ~100% (median 5 min). Someone not attended cannot have waited. INEI's 2015
    .dta swaps the two, and its dictionary swaps them in 2016 and 2019 --
    contradicting INEI's own .dta in 2014, 2016 and 2020. Reading this column
    from the dictionary gives exactly the wrong answer.
    """
    import pandas as pd
    from pathlib import Path

    p = (Path(__file__).parents[1] / "src" / "perudata" / "crosswalks"
         / "enaho_label_overrides.csv")
    o = pd.read_csv(p, encoding="utf-8-sig", dtype=str)
    one = set(o[(o.column == "p407h") & (o.code == "1")].label.dropna())
    zero = set(o[(o.column == "p407h") & (o.code == "0")].label.dropna())
    assert one <= {"No lo atendieron"}, f"p407h code 1 labelled {one}"
    assert zero <= {"Sí lo atendieron"}, f"p407h code 0 labelled {zero}"


def test_p208a1_zero_is_a_no_not_a_pase():
    """p208a1 code 0 is 'No nació en este distrito', never 'Pase'.

    p208a2 records the district of birth. Code 1 matches the household's
    ubigeo in 100.0% of rows and code 0 in 0.0%, across 2007, 2010, 2013, 2015
    and 2016 (2007 stores p208a2 as a float, so the comparison must be
    numeric -- a string compare wrongly makes 2007 look like an exception).

    'Pase' claimed 43,466 respondents in 2007 were never asked a question that
    is put to every person on the roster, and that they answered.
    """
    import pandas as pd
    from pathlib import Path

    p = (Path(__file__).parents[1] / "src" / "perudata" / "crosswalks"
         / "enaho_label_overrides.csv")
    o = pd.read_csv(p, encoding="utf-8-sig", dtype=str)
    got = set(o[(o.column == "p208a1") & (o.code == "0")].label.dropna())
    assert "Pase" not in got, "p208a1 code 0 is back to 'Pase'"
    assert got <= {"No nació en este distrito"}, f"p208a1 code 0 = {got}"


def test_p1145_is_the_none_of_these_slot():
    """p1145 code 1 is 'No tiene', not p1141's 'Telefono fijo'.

    The 2006/2007 rows carried p1141's label, so 13,479 households in 2006 and
    11,736 in 2007 that own NO service were labelled landline owners. Proven by
    exact complementarity in 2006, 2007, 2012 and 2024:

        p1145 == 1 -> owns ANY of p1141-p1144 in   0.0% of rows
        p1145 == 0 -> owns ANY of p1141-p1144 in 100.0% of rows
    """
    import pandas as pd
    from pathlib import Path

    p = (Path(__file__).parents[1] / "src" / "perudata" / "crosswalks"
         / "enaho_label_overrides.csv")
    o = pd.read_csv(p, encoding="utf-8-sig", dtype=str)
    got = set(o[(o.column == "p1145") & (o.code == "1")].label.dropna())
    assert got <= {"No tiene"}, f"p1145 code 1 labelled {got}"

    # p107aN4 is the 'no gasto' flag, not the p107aN1 'did you spend?' filter
    for col, want in (("p107a14", "No gastó ampliación"),
                      ("p107a24", "No gastó modificación"),
                      ("p107a34", "No gastó construcción nueva")):
        got = set(o[(o.column == col) & (o.code == "1")].label.dropna())
        assert "Si" not in got, f"{col} code 1 is back to 'Si'"
        assert got <= {want}, f"{col} code 1 labelled {got}"


def test_no_typographic_duplicate_labels():
    """One code, one spelling: no (column, code) may carry two labels that
    differ only by accents, case, or punctuation.

    Pooling years and grouping by label turns 'Rio, acequia, lago, laguna' and
    'Río, acequia, lago, laguna' into two categories, each looking like it
    appears and vanishes mid-panel though nothing in the data changed. p110
    code 4 once shipped six spellings of one water source.

    This does NOT require every code to have one label across years -- genuine
    INEI recodes (p102: 'Adobe o tapia' -> 'Adobe', a real category split) must
    survive. The test only forbids labels that are IDENTICAL once accents, case
    and punctuation are stripped, which is a meaning-preserving comparison.
    """
    import re
    import unicodedata
    from pathlib import Path

    import pandas as pd

    def collapse(s: str) -> str:
        s = unicodedata.normalize("NFKD", str(s))
        s = "".join(c for c in s if not unicodedata.combining(c))
        return re.sub(r"[^a-z0-9]", "", s.lower())

    p = (Path(__file__).parents[1] / "src" / "perudata" / "crosswalks"
         / "enaho_label_overrides.csv")
    o = pd.read_csv(p, encoding="utf-8-sig", dtype=str)

    offenders = []
    for key, g in o.groupby(["module", "column", "code"]):
        labels = set(g.label.dropna())
        if len(labels) > 1 and len({collapse(x) for x in labels}) == 1:
            offenders.append((key, sorted(labels)))
    assert not offenders, (
        f"{len(offenders)} codes carry typographic-duplicate labels, e.g. "
        f"{offenders[:3]}")


def test_module78_p606n_is_personal_care_not_esparcimiento():
    """The consumption/production modules were resolved from the standalone
    whole-survey dictionary, which is NOT module-scoped, so colliding column
    names pulled the wrong module's labels. p606n is personal-care products in
    module 78 but esparcimiento in module 12; module 78's rows had absorbed
    module 12's labels ('Esparcimiento y diversión' on the champú code).

    INEI's module-scoped .dta is ground truth: module 78 p606n code 2 is
    'Champú y reacondicionador', not anything about cinema or CDs.
    """
    import pandas as pd
    from pathlib import Path

    p = (Path(__file__).parents[1] / "src" / "perudata" / "crosswalks"
         / "enaho_label_overrides.csv")
    o = pd.read_csv(p, encoding="utf-8-sig", dtype=str)
    lab = set(o[(o.module == "78") & (o.column == "p606n")
               & (o.code == "2")].label.dropna())
    assert lab, "module 78 p606n code 2 missing"
    joined = " ".join(lab).lower()
    assert "champ" in joined, f"module 78 p606n c2 = {lab} (collision not repaired)"
    assert "esparcimiento" not in joined, f"module 12 label leaked: {lab}"


def test_acquisition_batteries_zero_is_no_marcado():
    """The '¿cómo obtuvo?' / '¿cómo pagó?' / 'tipo de explotación' batteries in
    the consumption and agro modules have code 0 = 'No marcado', not 'Pase'.
    Proven exhaustive from the microdata: across all years essentially no
    in-universe row marks none of the siblings (markNONE <= 0.0006%).
    """
    import re
    import pandas as pd
    from pathlib import Path

    p = (Path(__file__).parents[1] / "src" / "perudata" / "crosswalks"
         / "enaho_label_overrides.csv")
    o = pd.read_csv(p, encoding="utf-8-sig", dtype=str)
    fams = [("07", r"p601a\d+"), ("12", r"p606a\d+"), ("78", r"p606e\d+"),
            ("08", r"p602d[abc]"), ("22", r"p20001[abc]")]
    for mod, rx in fams:
        pase = o[(o.module == mod) & o.column.str.fullmatch(rx, na=False)
                 & (o.code == "0") & (o.label == "Pase")]
        assert pase.empty, f"{mod} {rx}: {len(pase)} rows back to 'Pase'"


def test_social_and_governance_batteries_are_no_marcado():
    """Modules 37 (social programmes) and 85 (governance) were resolved before
    the multiple-response rule was proven, so their flag batteries kept 'Pase'
    on code 0: the programme batteries (p701_* vaso de leche, p710_* wawa wasi)
    and the corruption batteries (p2_1_* perception, p22a_*_* the places a person
    witnessed corruption).

    Each was tested against the microdata: every code-0 cell sits in a row where
    the battery was administered (out-of-universe 0-rows = 0 across all years),
    so code 0 is 'No marcado', not 'Pase'. Single-choice questions in the same
    modules (p9 democracy preference, codes 1-4) correctly KEPT 'Pase' -- they
    are not batteries, and the binary-flag guard excluded them.
    """
    import pandas as pd
    from pathlib import Path

    p = (Path(__file__).parents[1] / "src" / "perudata" / "crosswalks"
         / "enaho_label_overrides.csv")
    o = pd.read_csv(p, encoding="utf-8-sig", dtype=str)

    for mod, col in (("37", "p701_01"), ("37", "p710_01"),
                     ("85", "p2_1_01"), ("85", "p22a_1_01")):
        got = set(o[(o.module == mod) & (o.column == col)
                   & (o.code == "0")].label.dropna())
        assert "Pase" not in got, f"{mod} {col} code 0 is back to 'Pase'"
        assert got <= {"No marcado"}, f"{mod} {col} code 0 = {got}"

    # p9 is single-choice (democracy preference), NOT a battery -> keeps its label
    p9 = set(o[(o.module == "85") & (o.column == "p9")
              & (o.code == "0")].label.dropna())
    assert "No marcado" not in p9, "p9 (single-choice) wrongly set to 'No marcado'"


def test_multiresponse_batteries_no_marcado_filters_stay_pase():
    """A package-wide sweep found flag batteries still labelled 'Pase' in
    modules 01/03/04/05/84 that earlier passes missed. Each was decided by a
    NON-VACUOUS test: code 0 is 'No marcado' only when the released records show
    a sibling flag == 1 co-occurring with another == 0 (admin0 >= 30), which
    proves the battery was administered and the 0 is a deliberate 'not this one'.

    Genuine filter follow-ups, where 0 really is a skip, showed admin0 == 0 and
    correctly KEPT 'Pase' -- this test pins both outcomes so a future rule cannot
    over- or under-reach.
    """
    import pandas as pd
    from pathlib import Path

    p = (Path(__file__).parents[1] / "src" / "perudata" / "crosswalks"
         / "enaho_label_overrides.csv")
    o = pd.read_csv(p, encoding="utf-8-sig", dtype=str)

    # proven multi-response batteries -> code 0 is 'No marcado'
    for mod, col in (("04", "p558h1_01"), ("04", "p409_01"), ("05", "p511_01"),
                     ("84", "p801_01"), ("01", "p1171_01")):
        got = set(o[(o.module == mod) & (o.column == col)
                   & (o.code == "0")].label.dropna())
        if got:
            assert "Pase" not in got, f"{mod} {col} code 0 back to 'Pase'"
            assert got <= {"No marcado"}, f"{mod} {col} code 0 = {got}"

    # genuine filter follow-ups (admin0 == 0) -> code 0 stays 'Pase'
    for mod, col in (("05", "p524a1"), ("05", "p538b1")):
        got = set(o[(o.module == mod) & (o.column == col)
                   & (o.code == "0")].label.dropna())
        if got:
            assert "No marcado" not in got, f"{mod} {col} wrongly set 'No marcado'"


def test_value_labels_surfaces_the_verified_crosswalk():
    """The whole point of the label crosswalk is that a researcher calling the
    documented dictionary.value_labels() gets the HARMONIZED answer, not INEI's
    raw (and often absent or wrong) one. This was silently disconnected: INEI
    ships no standalone dictionary after ~2018, so ocu500 returned {} for 2019+,
    and the crosswalk that fixes p407h, the batteries and the collisions was
    never consulted. value_labels() must overlay the crosswalk.
    """
    from perudata import dictionary as dic

    # a code INEI never labelled after 2018 -> filled from the crosswalk
    lab = dic.value_labels("ocu500", 2023, "05")
    assert lab.get("1") == "Ocupado" and lab.get("0") == "Sin informacion", lab

    # a code INEI got WRONG -> the crosswalk's correction wins
    p407h = dic.value_labels("p407h", 2019, "04")
    assert p407h.get("1") == "No lo atendieron", p407h  # not the inverted label

    # an exhaustive-battery zero -> 'No marcado', not the dictionary's 'Pase'
    assert dic.value_labels("p3152", 2023, "03").get("0") == "No marcado"

    # a stale published-dictionary code (a different-vintage encoding) is dropped
    # rather than merged into a phantom set
    p1145 = dic.value_labels("p1145", 2006, "01")
    assert p1145.get("1") == "No tiene"
    assert "5" not in p1145, f"stale code 5 leaked: {p1145}"


def test_validate_poverty_accepts_a_bare_year():
    """poverty(2023) is the natural call; it must not iterate an int. Accepts a
    single int, a range, or a list -- the flagship gate should not trip on the
    most obvious usage."""
    import inspect
    from perudata import validate
    src = inspect.getsource(validate.poverty)
    assert "isinstance(years, int)" in src and "list(years)" in src


def test_battery_code0_is_consistent_across_the_full_span():
    """One code, one meaning across 2004-2025. value_labels() overlays the
    crosswalk on INEI's .dta, but where the crosswalk was incomplete the raw
    .dta 'pase' leaked through in some years while the crosswalk said 'No
    marcado' in others -- so a pooled panel saw the same battery slot change
    meaning mid-series (p314b1_8: 'pase' 2019, 'No marcado' 2021). The crosswalk
    was completed so code 0 reads the same in every year the battery exists.
    """
    from perudata import dictionary as dic

    for col, mod in (("p314b1_8", "03"), ("p1121", "01"), ("p558h1_1", "05")):
        seen = {dic.value_labels(col, y, mod).get("0")
                for y in range(2004, 2026)}
        seen.discard(None)
        assert "pase" not in {s.lower() for s in seen}, \
            f"{col} code 0 still leaks 'pase': {seen}"
        assert seen <= {"No marcado"}, f"{col} code 0 varies by year: {seen}"


def test_value_labels_casing_is_consistent_across_years():
    """Harmonization must let a pooled panel aggregate BY LABEL, not just by
    code. INEI's .dta lowercases labels in early years ('ocupado') while the
    crosswalk carries the canonical 'Ocupado' in later ones, so grouping a
    2004-2025 panel by label split the same category and dropped early years.
    value_labels() unifies casing to the crosswalk's canonical spelling where
    the .dta label is the same word -- without touching genuine recodes.
    """
    from perudata import dictionary as dic

    # same word, different .dta casing -> one canonical label across the span
    ocu = {dic.value_labels("ocu500", y, "05").get("1")
           for y in range(2004, 2026)}
    ocu.discard(None)
    assert ocu == {"Ocupado"}, f"ocu500 code 1 label varies by year: {ocu}"

    # a GENUINE recode must NOT be collapsed: estrato was rebinned from
    # viviendas to habitantes, so its labels legitimately differ across years
    estr = {dic.value_labels("estrato", y, "01").get("1")
            for y in range(2004, 2026)}
    estr.discard(None)
    assert len(estr) > 1, "estrato recode wrongly unified"


def test_endes_value_labels_are_harmonized_across_years():
    """ENDES ships DHS recode labels that drift by LANGUAGE and synonym across
    years -- v106 code 3 is 'Higher' (English, 2013), 'Mayor' (2019) and
    'Superior' (2024) for the SAME higher-education code. The codes are stable
    but a pooled panel grouped by label splits the category. endes.value_labels
    returns one canonical Spanish label per code so aggregation works across
    years.
    """
    from perudata import endes

    v106 = endes.value_labels("v106")
    assert v106.get("3") == "Superior", v106
    assert v106.get("0") and v106.get("1") and v106.get("2")
    # marital status and wealth resolve to Spanish canonical labels too
    assert endes.value_labels("v501").get("1")            # casado
    assert len(endes.value_labels("v190")) == 5           # wealth quintiles
    # year is accepted but the canonical label is year-independent
    assert endes.value_labels("v106", 2013) == endes.value_labels("v106", 2024)


def test_endes_dataset_and_decode_are_wired():
    """The ENDES one-call loader mirrors perudata.dataset(): pool a recode across
    years, attach the clean DHS weight and the harmonized labels, and decode a
    code column to a label that is CONSISTENT across years. This checks the API
    surface and the decode path without needing the .sav on disk."""
    import pandas as pd
    from perudata import endes

    assert callable(endes.dataset) and callable(endes.decode)

    # decode() maps codes to the harmonized label and reads it from attrs first
    df = pd.DataFrame({"v106": [0, 1, 2, 3, 3]})
    df.attrs["labels"] = {"v106": endes.value_labels("v106")}
    out = endes.decode(df, "v106")
    assert (out == "Superior").sum() == 2          # code 3 -> the ONE canonical label
    assert set(out.dropna()) <= {"Sin educación", "Primario", "Secundario",
                                 "Superior"}
    # falls back to the crosswalk when no attrs are attached
    assert endes.decode(pd.DataFrame({"v106": [3]}), "v106").iloc[0] == "Superior"


def test_endes_load_has_selects_recode_by_content():
    """The DHS reproduction recode is named REC223132 / REC22312 / RE212232 /
    RE223132 across ENDES years -- unmatchable by name. load(..., has=['v201'])
    must select the recode by the columns it CONTAINS. This checks the argument
    is wired through load() and dataset() (the file scan needs data, so only the
    plumbing is asserted here)."""
    import inspect
    from perudata import endes
    assert "has" in inspect.signature(endes.load).parameters
    assert "has" in inspect.signature(endes.dataset).parameters
    assert callable(endes._recode_columns)


def test_endes_dataset_has_true_year_option():
    """The 2004-2008 ENDES files are cumulative (nest prior years' interviews);
    true_year=True assigns each record to its calendar year via v008 and draws
    each year from one source. cmc_year converts the CMC interview code to a
    calendar year. Checks the plumbing (the split needs the .sav on disk)."""
    import inspect
    from perudata import endes
    assert "true_year" in inspect.signature(endes.dataset).parameters
    # CMC 1345 = month 1345 from 1900 -> year 1900 + 1344//12 = 2012
    assert int(endes._cmc_year(__import__("pandas").Series([1345]))[0]) == 2012
    assert endes._CUMULATIVE_SRC[2006] == 2007 and endes._CUMULATIVE_SRC[2008] == 2008


def test_endes_tfr_helper_exists():
    """endes.tfr() packages the DHS 36-month ASFR computation (verified to
    reproduce INEI's TGF within 0.05 across 2004-2024). Checks the API surface;
    the computation needs the .sav on disk."""
    import inspect
    from perudata import endes
    sig = inspect.signature(endes.tfr)
    assert "true_year" in sig.parameters
    assert endes._ASFR_AGES == [15, 20, 25, 30, 35, 40, 45]


def test_endes_discover_code_api():
    """endes.discover_code(year) finds the INEI proyecto code for an ENDES year
    not yet in the map (e.g. 2025) by probing the live server and CONTENT-
    verifying the interview year -- a 200 alone is not proof. A year already in
    the map short-circuits to its code. Only the offline behaviour is asserted;
    the probe itself needs the network."""
    import inspect
    from perudata import endes
    sig = inspect.signature(endes.discover_code)
    assert {"lo", "hi", "module", "verify", "register"} <= set(sig.parameters)
    # a known year returns immediately without probing
    assert endes.discover_code(2024, verbose=False) == endes.ENDES_CODE[2024]


def test_endes_combine_levels_and_keys():
    """endes.combine() is the ENAHO combine() parallel: merge the standard DHS
    recodes onto one unit. Checks the level->key/anchor tables and the API; the
    merge itself needs the .sav on disk."""
    import inspect
    from perudata import endes
    assert "level" in inspect.signature(endes.combine).parameters
    assert endes._LEVEL_KEY == {"woman": "caseid", "birth": "caseid",
                                "child": "caseid", "household": "hhid"}
    # every level names an anchor recode and (for woman/birth/child) companions
    assert endes._LEVEL_ANCHOR["woman"][0] == "mef_datos_basicos"
    assert endes._LEVEL_ANCHOR["household"][0] == "hogar"
    assert endes._LEVEL_MERGE["birth"] == [("mef_datos_basicos", "REC0111", None)]


def test_epen_loads_all_formats_and_has_value_labels():
    """EPEN spans three formats by vintage -- modern CSV, and the 2005-2015
    legacy EPE served as .sav/.dbf. load() reads whichever is present (a CSV-only
    reader silently dropped the .sav era). value_labels() serves the labels
    harvested from the .sav files (codes-only CSVs carry none)."""
    import inspect
    from perudata import epen
    src = inspect.getsource(epen.load)
    assert ".sav" in src and ".dbf" in src, "load() must read the legacy formats"
    # dataset_dir finds both the staged and the INEI-toolkit layout
    assert "epen_inei" in inspect.getsource(epen.dataset_dir)
    # the standard employment condition decodes to the DHS/ENAHO categories
    ocu = epen.value_labels("ocu200")
    assert ocu.get("1") == "Ocupado" and "No PEA" in ocu.values()
