import math

import pytest

from pipette_cal.physics import (Environment, air_density, water_density,
                                 weight_to_volume, z_factor)


@pytest.mark.parametrize("t, expected", [(4.0, 999.975), (20.0, 998.207), (25.0, 997.047),
                                         (30.0, 995.650)])
def test_water_density_matches_reference_table(t, expected):
    assert water_density(t) == pytest.approx(expected, abs=0.01)


def test_air_density_at_standard_conditions():
    # ~1.20 kg/m3 at 20 C, 1013.25 hPa, 50 % RH
    assert air_density(20.0, 50.0, 1013.25) == pytest.approx(1.199, abs=0.003)


@pytest.mark.parametrize("t, expected", [(15.0, 1.0020), (20.0, 1.0029), (25.0, 1.0040),
                                         (30.0, 1.0054)])
def test_z_factor_matches_iso_8655_table(t, expected):
    # ISO 8655-6 Annex A Z-values at 1013 hPa (uL/mg)
    assert z_factor(Environment(t, 50.0, 1013.25)) == pytest.approx(expected, abs=0.0002)


def test_weight_to_volume():
    z = z_factor(Environment(20.0, 50.0))
    assert weight_to_volume(0.1, z) == pytest.approx(100.29, abs=0.02)


def test_environment_validation():
    with pytest.raises(ValueError):
        Environment(45.0, 50.0).validate()
    with pytest.raises(ValueError):
        Environment(20.0, 120.0).validate()
    with pytest.raises(ValueError):
        Environment(20.0, 50.0, 500.0).validate()
    Environment(22.0, 45.0, 1010.0).validate()
    assert math.isfinite(z_factor(Environment(22.0, 45.0, 1010.0)))
