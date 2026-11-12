import pytest

from pipette_cal.models import Level, get_spec
from pipette_cal.physics import Environment, z_factor
from pipette_cal.stats import evaluate

ENV = Environment(20.0, 50.0, 1013.25)


def grams_for(ul: float) -> float:
    """Mass in grams that converts back to exactly *ul* microlitres."""
    return ul / 1000.0 / z_factor(ENV)


def test_perfect_pipette_passes():
    spec = get_spec("P200")
    weights = {lv: [grams_for(spec.volume_for(lv))] * 4 for lv in Level}
    res = evaluate(spec, ENV, weights)
    assert res.passed and res.verdict == "PASS"
    for lv in res.levels:
        assert lv.mean_ul == pytest.approx(lv.nominal_ul, abs=1e-9)
        assert lv.systematic_error_ul == pytest.approx(0.0, abs=1e-9)
        assert lv.random_error_ul == pytest.approx(0.0, abs=1e-9)
        assert lv.accuracy_pct == pytest.approx(100.0)
        assert lv.uncertainty_ul > 0          # balance contribution remains


def test_systematic_error_fails_at_limit():
    spec = get_spec("P200")            # HIGH = 200 uL, sys limit 1.6 uL
    good = {lv: [grams_for(spec.volume_for(lv))] * 4 for lv in Level}
    bad = dict(good)
    bad[Level.HIGH] = [grams_for(201.7)] * 4
    res = evaluate(spec, ENV, bad)
    high = res.level(Level.HIGH)
    assert not high.systematic_pass and high.random_pass
    assert not res.passed
    assert high.systematic_error_ul == pytest.approx(1.7, abs=1e-6)
    assert high.systematic_error_pct == pytest.approx(0.85, abs=1e-6)


def test_random_error_fails():
    spec = get_spec("P1000")           # rnd limit 3.0 uL
    good = {lv: [grams_for(spec.volume_for(lv))] * 4 for lv in Level}
    bad = dict(good)
    bad[Level.MID] = [grams_for(v) for v in (495.0, 505.0, 495.0, 505.0)]   # SD ~5.77
    res = evaluate(spec, ENV, bad)
    mid = res.level(Level.MID)
    assert mid.systematic_pass and not mid.random_pass
    assert mid.random_error_ul == pytest.approx(5.7735, abs=1e-3)
    assert mid.cv_pct == pytest.approx(1.1547, abs=1e-3)


def test_requires_four_weights():
    spec = get_spec("P20")
    weights = {lv: [grams_for(spec.volume_for(lv))] * 4 for lv in Level}
    weights[Level.LOW] = weights[Level.LOW][:3]
    with pytest.raises(ValueError, match="LOW"):
        evaluate(spec, ENV, weights)


def test_invalid_environment_rejected():
    spec = get_spec("P20")
    weights = {lv: [grams_for(spec.volume_for(lv))] * 4 for lv in Level}
    with pytest.raises(ValueError):
        evaluate(spec, Environment(60.0, 50.0), weights)
