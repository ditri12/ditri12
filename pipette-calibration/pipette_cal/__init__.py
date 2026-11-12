"""Gilson pipette calibration tool for LifeGene Ltd.

Package layout
--------------
models       Pipette specifications, test volumes and acceptance limits.
physics      Gravimetric conversion: water density, air density, Z factor.
stats        Mean / SD / systematic & random error / uncertainty / pass-fail.
scale        RADWAG balance protocol (TCP) + a simulator for demo mode.
certificate  PDF calibration certificate (reportlab).
storage      Persistent configuration, calibration history, document numbers.
app          Tkinter desktop application.
"""

__version__ = "2.0.0"
__app_name__ = "LifeGene Pipette Calibration"
