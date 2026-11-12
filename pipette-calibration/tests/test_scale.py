import pytest

from pipette_cal.scale import SimulatedScale, parse_reading


@pytest.mark.parametrize("line, value, stable", [
    ("SI   -  0.000070 g", -0.000070, True),
    ("SI      0.012345 g", 0.012345, True),
    ("SI ?    0.012345 g", 0.012345, False),
    ("SI ?  - 0.000040 g", -0.000040, False),
    ("SI XS   0.100000 g", 0.1, True),
    ("SI XI   0.100000 g", 0.1, False),
    ("S    +  1.5 g", 1.5, True),
    ("-0.000040 g", -0.000040, True),
    ("SI   -  70.0 mg", -0.07, True),
])
def test_parse_reading(line, value, stable):
    r = parse_reading(line + "\r\n")
    assert r is not None
    assert r.value_g == pytest.approx(value, abs=1e-9)
    assert r.stable is stable
    assert r.raw == line.strip()


@pytest.mark.parametrize("line", ["", "Z_A", "T_A", "ES", "SI_E"])
def test_parse_noise_returns_none(line):
    assert parse_reading(line) is None


def test_sign_is_preserved_in_formatting():
    assert parse_reading("SI   -  0.000070 g").formatted() == "-0.000070"
    assert parse_reading("SI      0.000070 g").formatted() == "+0.000070"


def test_simulated_scale_roundtrip():
    s = SimulatedScale(poll_interval=0.01, seed=1)
    s.connect()
    assert s.read_once().value_g == pytest.approx(0.0, abs=1e-4)
    s.add_drop(0.1)
    s._settle_until = 0          # skip settling for a deterministic test
    r = s.read_once()
    assert r.stable and r.value_g == pytest.approx(0.1, abs=0.002)
    s.tare()
    assert s.read_once().value_g == pytest.approx(0.0, abs=1e-4)
    s.start_listening()
    reading = s.readings.get(timeout=2.0)
    assert reading is not None
    s.disconnect()
    assert not s.listening and not s.connected
