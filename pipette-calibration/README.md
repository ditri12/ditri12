# LifeGene Pipette Calibration

Desktop program for the gravimetric calibration of Gilson pipettes with a
RADWAG analytical balance. It reads the balance live, records 4 weights at
the LOW / MID / HIGH test volume, converts them to volume, checks the
systematic and random error against the lab's acceptance limits and produces
a two-page PDF calibration certificate.

![Measurements tab](docs/screenshots/04_measurements_progress.png)

## What is new in version 2

Version 1 was a single 40 KB script. Version 2 is the same workflow rebuilt as
a small, tested application:

* **Package structure** - physics, statistics, balance protocol, certificate,
  storage and GUI are separate modules with 40 unit tests (`pytest`).
* **Correct physics** - Z factor from water density (Tanaka 2001) and an air
  buoyancy correction; values match the ISO 8655-6 reference table.
  The Environment tab shows water density, air density and Z live.
* **Expanded uncertainty (k = 2)** per test volume on screen and on the certificate.
* **Demo mode** - a built-in balance simulator, so the program can be learned,
  demonstrated and tested without hardware ("Simulate drop" button).
* **Robust balance link** - background polling thread, tolerant parser
  (detached sign, `?`, `XS`/`XI`, `g`/`mg`), automatic reconnect message after
  repeated errors, Tare after every saved reading, Enter saves.
* **Calibration history** - every calculation is stored in a local SQLite
  database (document number, pipette, verdict, all raw weights). Document
  numbers are generated automatically (`LG-CAL-2026-0001`, ...), a certificate
  can be re-created from history at any time, and the Setup tab warns when a
  serial number was calibrated before.
* **Settings dialog** - operator name, e-mail recipient, balance readability,
  default environment, PDF folder, next-calibration interval. Stored per user
  in `%APPDATA%\LifeGene\PipetteCalibration`.
* **Certificate** - two pages, no clipped text, colour-coded LOW / MID / HIGH
  tables, limits and PASS/FAIL per criterion, weights and volumes, bold
  scope-of-calibration notice, LifeGene contact details, page footer.
* **Dark / light theme**, maximised window, logo from `assets/logo.png`.
* **Windows helpers** - `install.bat`, `run.bat`, and `build_exe.bat`
  (PyInstaller) to hand out a single `PipetteCalibration.exe`.

## Installation (Windows)

1. Install Python 3.10 or newer from python.org (tick *Add python to PATH*).
2. Copy this folder anywhere (e.g. `C:\PipetteCalibration`).
3. Double-click `install.bat` once.
4. Start the program with `run.bat`, or

```bash
python gilson_calibration.py
```

Optional: put the company logo in `assets/logo.png` (PNG, 400 px high or more).
For e-mail through Outlook the `pywin32` package is installed by `install.bat`;
without Outlook the default mail client opens instead.

## Daily use

1. **Setup** - choose the model, enter the serial number. Tip, document number,
   calibration date, next calibration (+12 months) and place are filled in
   automatically and can be edited.
2. **Environment** - water temperature, humidity, pressure, balance ID.
3. **Measurements** - *Connect* (IP 10.0.0.112 : 4001 by default). The live
   reading is always shown. Dispense the test volume and press **Enter**
   (or *Save reading*); the program stores the weight, tares the balance and
   moves to the next slot. *Zero* / *Tare* / *Undo last* / per-slot ✕ are
   available. After the 12th weight the results are calculated automatically.
4. **Results** - PASS / FAIL with all figures. Nothing is saved to disk until
   you choose **Save PDF**, **Print** or **Email** in the footer.
5. **History** - search past calibrations, re-create a PDF, or load one back
   into the form.

## Pipette models and limits

Single channel P2, P10, P20, P100, P200, P1000, P5000, P10mL and
multichannel P8x / P12x 10, 20, 200, 300, 1200. Test volumes and the
systematic / random error limits are listed in `pipette_cal/models.py`; see
`docs/PROTOCOL.md` for the formulas and the balance protocol.

## Development

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
python -m pipette_cal
```

| Module | Purpose |
|--------|---------|
| `pipette_cal/models.py` | pipette specs, test volumes, acceptance limits |
| `pipette_cal/physics.py` | water / air density, Z factor, weight to volume |
| `pipette_cal/stats.py` | mean, SD, errors, CV, uncertainty, pass/fail |
| `pipette_cal/scale.py` | RADWAG TCP protocol, parser, polling thread, simulator |
| `pipette_cal/certificate.py` | PDF certificate (reportlab) |
| `pipette_cal/storage.py` | settings file, SQLite history, document numbers |
| `pipette_cal/report.py` | open / print / e-mail the PDF |
| `pipette_cal/app.py` | Tkinter GUI |

The calibration is an internal, non-accredited procedure. The certificate
says so explicitly; do not remove that notice.
