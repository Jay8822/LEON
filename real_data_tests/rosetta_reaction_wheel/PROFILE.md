# Rosetta Reaction Wheel Engineering Data — profile

Item 4d of the 26 October 2026 round (`Ccode update.txt`). **Look
only — a small sample downloaded and profiled, no scoring/testing
code built this round.** This is for LUNAE (navigation) later, per
Jay's own instruction, not acted on now.

## What it is

Real housekeeping telemetry from the four reaction wheels on ESA's
Rosetta spacecraft (the comet-chasing mission, 67P/
Churyumov-Gerasimenko), spanning launch in 2004 through to the
mission's end in 2016 — including the real ~2.5-year hibernation gap
(2011 Q2 to 2014 Q1, confirmed directly: the directory listing simply
has no files for those quarters, matching the known mission history).
Published on NASA's Planetary Data System / ESA's Planetary Science
Archive. Cite: O'Rourke, Heather, Andres, "Rosetta Spacecraft Reaction
Wheel Engineering Data," RO-X-HK-3-RWL-V1.0, 2020. Licence: US
government works.

## Five real parameters, four wheels each, confirmed by downloading and inspecting two of them directly

Directory structure: `data/<parameter>/<year>_q<N>/` with one PDS3
label (`.lbl`, plain text metadata) + table (`.tab`, ASCII) pair per
wheel. Five parameters: `rwl_est_frict_torque`, `rwl_frict_coeff`,
`rwl_meas_ang_mom`, `rwl_wheel_direction`, `rwl_wheel_speed`. Checked
directly (not assumed from the abstract, which only names three of
the five):

- **Wheel direction** (`rwl_wheel_direction`): one quarter (2016 Q1)
  for one wheel is 502,807 rows, ~16-second sampling, integer VALUE
  column (`0` in every sampled row this round — direction encoding,
  e.g. 0/1/-1, not independently confirmed beyond zero since the
  craft wasn't changing direction in the rows checked).
- **Wheel speed** (`rwl_wheel_speed`): real continuous values in RPM
  — confirmed directly, e.g. 313.0–315.0 rpm across the first several
  samples of 2016 Q1, ~64-second sampling.
- `rwl_est_frict_torque`, `rwl_frict_coeff`, `rwl_meas_ang_mom` —
  directory structure confirmed to exist (same per-wheel, per-quarter
  layout), contents not individually downloaded/inspected this round.

Total dataset size is ~1.6 GB across all parameters/wheels/quarters —
only one quarter of two parameters (one wheel each) was fetched this
round (~26 MB total), per "profile only, not this round."

## Honest limits

- No fault/anomaly labels of any kind — this is pure real engineering
  telemetry, same category as ESA-ADB/OPS-SAT's nominal portions, not
  a labelled test set.
- Sampling rate varies by parameter (16s for direction, 64s for
  speed, friction torque/coefficient/angular momentum not checked) —
  any future test would need to confirm each parameter's own rate,
  not assume one.
- Only one wheel of four checked per parameter — not confirmed
  whether all four wheels share the same sampling rate/format
  (reasonable to expect so, given the matching label structure seen,
  but not independently verified for wheels 2–4).

## What this means for later rounds (not decided now)

A real, long-duration (12 real years, with a genuine multi-year gap)
navigation-subsystem dataset — the first real candidate this project
has for LUNAE specifically, which currently has no real-data test at
all. Any actual test plan is a separate, later round, ambiguities
first, same as every other dataset decision this session.
