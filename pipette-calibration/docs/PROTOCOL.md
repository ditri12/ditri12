# Balance protocol and calculation notes

## RADWAG over TCP

| Item | Value |
|------|-------|
| Address | 10.0.0.112 : 4001 (default, editable in the app) |
| Line ending | CR LF |
| `SI` | send the current reading immediately (stable or not) |
| `Z` | zero the balance |
| `T` | tare the balance (sent automatically after every saved reading) |

Reply examples the parser understands:

```
SI   -  0.000070 g        stable, negative (the sign is a separate token)
SI ?    0.012345 g        unstable ("?")
SI XS   0.012345 g        stable  (firmware that reports XS / XI)
```

The parser (`pipette_cal/scale.py`, `parse_reading`) is token based, so extra
spaces, a detached sign and the unit (`g`, `mg`) are all handled.
Acknowledgements such as `Z_A` / `T_A` are ignored.

## From weight to volume

```
V [uL] = m [mg] x Z [uL/mg]
Z      = 1000 / (rho_water - rho_air) x (1 - rho_air / 8000)
```

* `rho_water` - Tanaka et al. (2001) formula, kg/m3, from the water temperature
* `rho_air`   - simplified CIPM formula from air temperature, humidity and pressure
* `8000`      - conventional density of the balance's steel reference weights

At 20 C / 50 % RH / 1013 hPa, Z = 1.0029 uL/mg.

## Statistics (per test volume, n = 4)

| Quantity | Formula |
|----------|---------|
| Mean volume | average of the 4 volumes |
| Systematic error | mean - nominal (uL and % of nominal) |
| Random error | sample standard deviation of the 4 volumes (uL), and SD / nominal x 100 % |
| CV | SD / mean x 100 % (shown on screen next to the random error %) |
| Expanded uncertainty U | 2 x sqrt( (SD / sqrt n)^2 + (readability x Z / (2 sqrt 3))^2 ) |

A test volume passes when `|systematic error| <= systematic limit` **and**
`random error <= random limit` for the pipette model (see `pipette_cal/models.py`).
The calibration passes when all three test volumes pass.

These are the laboratory's internal acceptance limits; the certificate states
explicitly that the calibration is not accredited.

## Differences from the original single-file program

| Topic | v1 (gilson_calibration.py) | v2 |
|-------|----------------------------|----|
| Water density | 16-entry table, 15-30 C, rounded to 1 C | Tanaka formula, 0-40 C |
| Z factor | 1 / density (no buoyancy) | with air-buoyancy correction (ISO 8655-6 values) |
| Uncertainty | 2 x SD / sqrt(n) | 2 x sqrt((SD / sqrt n)^2 + balance readability term) |
| Balance | one socket, read on the Tk thread | worker thread + queue, tolerant parser, simulator |
| Records | none | SQLite history, automatic document numbers, re-print |
| Tests | none | pytest suite |

At typical lab conditions the Z factor differs by about 0.1 % between the two
methods (1.0022 vs 1.0033 mL/g at 22 C); v2 is the standard gravimetric value.
