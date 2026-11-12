"""Pipette specifications and acceptance limits.

The limits below were confirmed with the lab during the original project.
They are internal acceptance limits (not ISO 8655 class limits): one
systematic-error limit (|mean - nominal|) and one random-error limit (SD),
both in microlitres, applied to all three test volumes of a model.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Level(str, Enum):
    LOW = "LOW"
    MID = "MID"
    HIGH = "HIGH"

    @property
    def index(self) -> int:
        return ("LOW", "MID", "HIGH").index(self.value)


LEVELS: tuple[Level, Level, Level] = (Level.LOW, Level.MID, Level.HIGH)
REPLICATES = 4  # weights per test volume


@dataclass(frozen=True)
class PipetteSpec:
    model: str                      # e.g. "P200", "P8x200"
    family: str                     # "single" or "multi"
    channels: int
    test_volumes: tuple[float, float, float]   # LOW / MID / HIGH in uL
    sys_limit_ul: float             # |systematic error| limit, uL
    rnd_limit_ul: float             # random error (SD) limit, uL
    default_tip: str

    @property
    def min_volume(self) -> float:
        return self.test_volumes[0]

    @property
    def max_volume(self) -> float:
        return self.test_volumes[2]

    @property
    def range_label(self) -> str:
        lo, hi = self.min_volume, self.max_volume
        if hi >= 1000:
            return f"{lo / 1000:g} - {hi / 1000:g} mL"
        return f"{lo:g} - {hi:g} uL"

    @property
    def display_name(self) -> str:
        if self.family == "multi":
            return f"{self.model}  ({self.channels}-ch, {self.range_label})"
        return f"{self.model}  ({self.range_label})"

    def volume_for(self, level: Level) -> float:
        return self.test_volumes[level.index]


def _single(model, vols, sys_, rnd, tip) -> PipetteSpec:
    return PipetteSpec(model, "single", 1, vols, sys_, rnd, tip)


def _multi(channels, size, vols, sys_, rnd, tip) -> PipetteSpec:
    return PipetteSpec(f"P{channels}x{size}", "multi", channels, vols, sys_, rnd, tip)


SINGLE_CHANNEL: tuple[PipetteSpec, ...] = (
    _single("P2",    (0.2, 1.0, 2.0),       0.08, 0.04, "D10"),
    _single("P10",   (1.0, 5.0, 10.0),      0.12, 0.08, "D10"),
    _single("P20",   (2.0, 10.0, 20.0),     0.20, 0.10, "D200"),
    _single("P100",  (10.0, 50.0, 100.0),   0.80, 0.30, "D200"),
    _single("P200",  (20.0, 100.0, 200.0),  1.60, 0.60, "D200"),
    _single("P1000", (100.0, 500.0, 1000.0), 8.0, 3.0,  "D1000"),
    _single("P5000", (500.0, 2500.0, 5000.0), 40.0, 15.0, "D5000"),
    _single("P10mL", (1000.0, 5000.0, 10000.0), 60.0, 30.0, "D10mL"),
)

_MULTI_SIZES = (
    # size, volumes, sys, rnd, tip
    (10,   (1.0, 5.0, 10.0),       0.24, 0.16, "D10"),
    (20,   (2.0, 10.0, 20.0),      0.40, 0.20, "D200"),
    (200,  (20.0, 100.0, 200.0),   3.20, 1.20, "D200"),
    (300,  (30.0, 150.0, 300.0),   8.00, 3.00, "D300"),
    (1200, (120.0, 600.0, 1200.0), 32.0, 12.0, "D1200"),
)

MULTI_CHANNEL: tuple[PipetteSpec, ...] = tuple(
    _multi(ch, size, vols, s, r, tip)
    for ch in (8, 12)
    for size, vols, s, r, tip in _MULTI_SIZES
)

ALL_SPECS: tuple[PipetteSpec, ...] = SINGLE_CHANNEL + MULTI_CHANNEL
SPECS_BY_MODEL: dict[str, PipetteSpec] = {s.model: s for s in ALL_SPECS}


def get_spec(model: str) -> PipetteSpec:
    """Look up a spec by model name (case-insensitive, tolerant of spaces)."""
    key = model.strip().replace(" ", "").lower()
    for spec in ALL_SPECS:
        if spec.model.lower() == key:
            return spec
    raise KeyError(f"Unknown pipette model: {model!r}")


def model_names(family: str | None = None) -> list[str]:
    return [s.model for s in ALL_SPECS if family is None or s.family == family]
