# NASA Li-ion Battery Aging Dataset (ARC) — profile

The dataset previously on hold (unreachable from this machine via
NASA DASHlink/c3.nasa.gov — see `real_data_tests/adapt/PROFILE.md`
for the same infrastructure problem). Jay downloaded it manually and
added it directly under `data/` (gitignored, same convention as every
other dataset here — see `.gitignore`). **Look only, this round** —
profiled, not scored; see `sim/RESULTS.md` for what this unblocks.

## Citation / licence

NASA Ames Prognostics Center of Excellence (PCoE), Li-ion Battery
Aging Dataset ("BatteryAgingARC"). Public NASA technical data —
`data/1. BatteryAgingARC-FY08Q4.zip`'s own `README.txt` is the
primary source for everything below; quoted/paraphrased from it
directly, not assumed.

## What it actually is

Four 18650 Li-ion batteries (#5, #6, #7, #18) run through repeated
charge/discharge/impedance cycles at room temperature until each hit
an end-of-life criterion: **30% capacity fade (2.0 Ahr → 1.4 Ahr)**.
Charge: constant-current (1.5A) to 4.2V, then constant-voltage until
current drops to 20mA. Discharge: constant-current (2A) to a cutoff
voltage specific to each battery (2.7V / 2.5V / 2.2V / 2.5V for
batteries 5/6/7/18 respectively). Impedance: an EIS frequency sweep,
0.1Hz–5kHz, for internal-parameter tracking.

Six zip archives total (`1.` through `6.`), covering battery groups
5-7/18, then 25-28, 25-44, 45-48, 49-52, 53-56 — only the first
(`1. BatteryAgingARC-FY08Q4.zip`, batteries 5/6/7/18) was opened and
inspected this round; the rest are the same format, listed but not
yet read.

## Fields (per cycle, `.mat` structure)

Each file (`B0005.mat` etc.) holds a `cycle` array, one entry per
charge/discharge/impedance operation, each carrying `type`,
`ambient_temperature`, `time`. Per-cycle `data` fields:
- **Charge**: `Voltage_measured`, `Current_measured`,
  `Temperature_measured`, `Current_charge`, `Voltage_charge`, `Time`.
- **Discharge**: same four plus `Capacity` (Ahr, the direct
  remaining-life signal) and `Voltage_charge`/`Current_charge` at the
  load.
- **Impedance**: `Sense_current`, `Battery_current`,
  `Current_ratio`, `Battery_impedance`, `Rectified_impedance`, `Re`
  (electrolyte resistance), `Rct` (charge-transfer resistance).

Directly matches `sim/blueprint.py`'s `battery_voltage`/
`battery_current` channels, plus a genuine `Temperature_measured`
this project's simulated craft doesn't currently have on the battery
specifically (it only has `engine_bay_temp`/`avionics_bay_temp`).

## What this unblocks (not done this round)

The simulated craft's `dying_battery` fault currently uses a
SYNTHETIC decline curve (Item 3's honest fallback, taken when this
dataset was unreachable). This dataset's real `Capacity` trace,
cycle to cycle, down to the real 30%-fade EOL point, is exactly the
"real measured decline, not invented" Jay's original Item 3 answer
asked for. Swapping it in is queued for a later round (after Jay's
usage resets), with its own commissioning/re-test, not built now.

## Honest limits

- Only the first of six archives opened; the other five are assumed
  same-format, not verified.
- Real battery EOL here is defined by a 30% capacity fade from a
  2.0Ahr nominal rating — a real lab rating for this specific battery
  model, not a number this project can claim applies to any other
  battery or mission.
- Still anonymised/lab data, not flight telemetry — same honest-limit
  category as OPS-SAT/ESA-ADB, stated plainly if this is ever used.
