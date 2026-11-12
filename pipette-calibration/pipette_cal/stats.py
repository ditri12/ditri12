"""Statistical evaluation of a calibration run."""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

from .models import LEVELS, REPLICATES, Level, PipetteSpec
from .physics import Environment, weight_to_volume, z_factor

COVERAGE_FACTOR = 2.0   # k = 2  (approx. 95 % confidence)


@dataclass(frozen=True)
class LevelResult:
    level: Level
    nominal_ul: float
    weights_g: tuple[float, ...]
    volumes_ul: tuple[float, ...]
    mean_ul: float
    sd_ul: float
    systematic_error_ul: float      # mean - nominal
    systematic_error_pct: float     # relative to nominal
    random_error_ul: float          # = SD
    random_error_pct: float         # SD / nominal * 100 (as on the certificate)
    cv_pct: float                   # SD / mean * 100
    uncertainty_ul: float           # expanded uncertainty of the mean, k = 2
    sys_limit_ul: float
    rnd_limit_ul: float

    @property
    def systematic_pass(self) -> bool:
        return abs(self.systematic_error_ul) <= self.sys_limit_ul + 1e-9

    @property
    def random_pass(self) -> bool:
        return self.random_error_ul <= self.rnd_limit_ul + 1e-9

    @property
    def passed(self) -> bool:
        return self.systematic_pass and self.random_pass

    @property
    def accuracy_pct(self) -> float:
        """Average accuracy of the replicates, as a percentage (100 = perfect)."""
        return 100.0 - abs(self.systematic_error_pct)


@dataclass(frozen=True)
class CalibrationResult:
    spec: PipetteSpec
    environment: Environment
    z: float
    levels: tuple[LevelResult, LevelResult, LevelResult]
    balance_readability_mg: float = 0.001

    @property
    def passed(self) -> bool:
        return all(lv.passed for lv in self.levels)

    @property
    def verdict(self) -> str:
        return "PASS" if self.passed else "FAIL"

    def level(self, level: Level) -> LevelResult:
        return self.levels[level.index]


def _uncertainty(sd_ul: float, n: int, readability_mg: float, z: float) -> float:
    """Expanded uncertainty (k = 2) of the mean volume.

    Combines the type-A standard uncertainty of the mean (SD / sqrt n) with
    the balance readability contribution (rectangular distribution).
    """
    u_a = sd_ul / math.sqrt(n) if n > 1 else 0.0
    u_balance = (readability_mg * z) / (2.0 * math.sqrt(3.0))
    return COVERAGE_FACTOR * math.sqrt(u_a ** 2 + u_balance ** 2)


def evaluate_level(spec: PipetteSpec, level: Level, weights_g: list[float],
                   z: float, readability_mg: float) -> LevelResult:
    if len(weights_g) < 2:
        raise ValueError(f"{level.value}: at least 2 weights are required.")
    for w in weights_g:
        if not math.isfinite(w) or w < 0:
            raise ValueError(f"{level.value}: invalid weight {w!r}.")
    nominal = spec.volume_for(level)
    volumes = [weight_to_volume(w, z) for w in weights_g]
    mean = statistics.fmean(volumes)
    sd = statistics.stdev(volumes)
    sys_err = mean - nominal
    return LevelResult(
        level=level,
        nominal_ul=nominal,
        weights_g=tuple(weights_g),
        volumes_ul=tuple(volumes),
        mean_ul=mean,
        sd_ul=sd,
        systematic_error_ul=sys_err,
        systematic_error_pct=(sys_err / nominal * 100.0) if nominal else 0.0,
        random_error_ul=sd,
        random_error_pct=(sd / nominal * 100.0) if nominal else 0.0,
        cv_pct=(sd / mean * 100.0) if mean else 0.0,
        uncertainty_ul=_uncertainty(sd, len(volumes), readability_mg, z),
        sys_limit_ul=spec.sys_limit_ul,
        rnd_limit_ul=spec.rnd_limit_ul,
    )


def evaluate(spec: PipetteSpec, env: Environment,
             weights: dict[Level, list[float]],
             balance_readability_mg: float = 0.001) -> CalibrationResult:
    """Evaluate a full calibration (3 levels x REPLICATES weights in grams)."""
    env.validate()
    z = z_factor(env)
    results = []
    for level in LEVELS:
        ws = weights.get(level) or []
        if len(ws) != REPLICATES:
            raise ValueError(
                f"{level.value}: expected {REPLICATES} weights, got {len(ws)}.")
        results.append(evaluate_level(spec, level, ws, z, balance_readability_mg))
    return CalibrationResult(spec, env, z, tuple(results), balance_readability_mg)
