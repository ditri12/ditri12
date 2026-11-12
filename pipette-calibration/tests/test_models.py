import pytest

from pipette_cal.models import (ALL_SPECS, LEVELS, Level, get_spec, model_names,
                                SPECS_BY_MODEL)


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
    assert [lv.index for lv in LEVELS] == [0, 1, 2]
