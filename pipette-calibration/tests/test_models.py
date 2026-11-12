import pytest

from pipette_cal.models import (ALL_SPECS, CATALOGUE, LEVELS, Level, full_model_name, get_spec,
                                model_names, resolve_catalogue_name, series_for, short_model_name,
                                SPECS_BY_MODEL, type_description)


def test_all_models_present():
    assert len(ALL_SPECS) == 8 + 2 * 5
    assert len(SPECS_BY_MODEL) == len(ALL_SPECS)
    assert model_names("single")[0] == "P2"
    assert "P8x200" in model_names("multi") and "P12x1200" in model_names("multi")


def test_lookup_is_tolerant():
    assert get_spec("p200").model == "P200"
    assert get_spec(" P8 x 200 ").model == "P8x200"
    with pytest.raises(KeyError):
        get_spec("P999")


def test_volumes_are_ordered_and_limits_positive():
    for spec in ALL_SPECS:
        lo, mid, hi = spec.test_volumes
        assert lo < mid < hi
        assert spec.sys_limit_ul > 0 and spec.rnd_limit_ul > 0
        assert spec.volume_for(Level.HIGH) == hi


def test_range_label():
    assert get_spec("P200").range_label == "20 - 200 uL"
    assert get_spec("P10mL").range_label == "1 - 10 mL"
    assert get_spec("P8x10").display_name.startswith("P8x10  (8-ch")
    assert get_spec("P200").default_tip == "DF200" and get_spec("P2").default_tip == "GS-10"


def test_catalogue_matches_original_program():
    names = [n for n, _, _ in CATALOGUE]
    assert len(names) == 30 and names[0] == "PIPETMAN Classic P2" and names[4] == "PIPETMAN Classic P200"
    assert "PIPETMAN Neo P200N" in names and "PIPETMAN L P1000L" in names
    assert "PIPETMAN Neo P5000N" not in names and "PIPETMAN Multi P12x1200" in names
    spec, series = resolve_catalogue_name("PIPETMAN L P200L")
    assert spec.model == "P200" and series == "L"
    assert short_model_name(spec, series) == "L P200L"
    assert full_model_name(get_spec("P8x200"), "Multi") == "PIPETMAN Multi P8x200"
    assert resolve_catalogue_name("P10mL")[1] == "Classic"
    assert series_for(get_spec("P5000")) == ("Classic",)
    assert type_description(get_spec("P12x20")) == "Variable: 12 channels"
    assert [lv.index for lv in LEVELS] == [0, 1, 2]
