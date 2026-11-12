"""Gravimetric conversion of balance readings to dispensed volume.

V = m * Z

* m  - mass of the dispensed water (mg)
* Z  - conversion factor (uL/mg) that corrects for the density of water at
       the test temperature and for air buoyancy acting on the water and on
       the balance's reference weights.

Formulas
--------
Water density: Tanaka et al., Metrologia 38 (2001) 301-309 (air-free SMOW),
valid 0-40 C, uncertainty well below 1e-3 kg/m3 - far smaller than anything
a pipette calibration can resolve.

Air density: the simplified CIPM formula used in ISO 8655-6 Annex A /
EURAMET guides:  rho_a = (0.34848 p - 0.009 h exp(0.061 t)) / (273.15 + t)
with p in hPa, h in % RH, t in C.

Z factor:      Z = 1 / (rho_w - rho_a) * (1 - rho_a / rho_b),  rho_b = 8000 kg/m3
(stainless-steel reference weights). Result in mL/g == uL/mg.
"""
from __future__ import annotations

from dataclasses import dataclass

STEEL_DENSITY = 8000.0          # kg/m3, conventional density of reference weights
STANDARD_PRESSURE_HPA = 1013.25


@dataclass(frozen=True)
class Environment:
    temperature_c: float
    humidity_pct: float
    pressure_hpa: float = STANDARD_PRESSURE_HPA

    def validate(self) -> None:
        if not 0.0 <= self.temperature_c <= 40.0:
            raise ValueError("Water temperature must be between 0 and 40 C.")
        if not 0.0 <= self.humidity_pct <= 100.0:
            raise ValueError("Relative humidity must be between 0 and 100 %.")
        if not 800.0 <= self.pressure_hpa <= 1100.0:
            raise ValueError("Air pressure must be between 800 and 1100 hPa.")


def water_density(temperature_c: float) -> float:
    """Density of air-free water in kg/m3 (Tanaka 2001)."""
    a1, a2, a3, a4, a5 = -3.983035, 301.797, 522528.9, 69.34881, 999.974950
    t = temperature_c
    return a5 * (1.0 - ((t + a1) ** 2 * (t + a2)) / (a3 * (t + a4)))


def air_density(temperature_c: float, humidity_pct: float,
                pressure_hpa: float = STANDARD_PRESSURE_HPA) -> float:
    """Density of moist air in kg/m3 (simplified CIPM formula)."""
    import math
    t = temperature_c
    return (0.34848 * pressure_hpa - 0.009 * humidity_pct * math.exp(0.061 * t)) / (273.15 + t)


def z_factor(env: Environment) -> float:
    """Conversion factor in uL/mg (equivalently mL/g)."""
    rho_w = water_density(env.temperature_c)
    rho_a = air_density(env.temperature_c, env.humidity_pct, env.pressure_hpa)
    # (1/(rho_w - rho_a)) is in m3/kg; multiply by 1000 to get mL/g.
    return 1000.0 / (rho_w - rho_a) * (1.0 - rho_a / STEEL_DENSITY)


def weight_to_volume(mass_g: float, z: float) -> float:
    """Convert a balance reading in grams to a dispensed volume in uL."""
    return mass_g * 1000.0 * z
