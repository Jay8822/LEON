# NASA Randomized Battery Usage Dataset family — profile

**"RW" in every folder/file name here means RANDOM WALK (a randomised
battery load pattern) — it has NOTHING to do with reaction wheels.**
Never confuse these with `real_data_tests/rosetta_reaction_wheel/` or
`real_data_tests/reaction_wheel_synthetic/` (navigation hardware,
unrelated). Jay added these manually; consolidated here under one
clearly-named folder specifically to make that confusion impossible.
Look only, this round — profiled, not scored.

## Citation / licence

NASA Ames Prognostics Center of Excellence (PCoE), "Randomized
Battery Usage Data Set." Each variant's own `README_RW_*.Rmd`/`.html`
(kept alongside its data here) is NASA's own documentation, by Brian
Bole, point of contact chetan.s.kulkarni@nasa.gov. Cite:
*Bole, Kulkarni, Daigle, "Adaptation of an Electrochemistry-based
Li-Ion Battery Model to Account for Deterioration Observed Under
Randomized Use," PHM Society Annual Conference, 2014.*

## The six variants

All are four-battery sets of 18650 Li-ion cells, repeatedly
charged/discharged under a randomised load, periodically interrupted
by reference charge/discharge cycles for health benchmarking —
exactly the same aging-under-use idea as the ARC dataset
(`real_data_tests/nasa_liion_battery_aging/`), but with a realistic
randomised duty cycle instead of a fixed charge/discharge profile.

| Folder | Batteries | Load pattern | Ambient |
|---|---|---|---|
| `Battery_Uniform_Distribution_Charge_Discharge_DataSet_2Post` | RW9-12 | Uniform, -4.5A to 4.5A (charge AND discharge), 5-min periods | Room temp |
| `Battery_Uniform_Distribution_Discharge_Room_Temp_DataSet_2Post` | (not opened this round) | Uniform, discharge only | Room temp |
| `Battery_Uniform_Distribution_Variable_Charge_Room_Temp_DataSet_2Post` | (not opened this round) | Uniform, variable charge | Room temp |
| `RW_Skewed_High_Room_Temp_DataSet_2Post` | RW17-20 | Skewed toward HIGH discharge current, 0.5A-5A, 1-min periods | Room temp |
| `RW_Skewed_High_40C_DataSet_2Post` | (not opened this round) | Same skew-high pattern | 40°C |
| `RW_Skewed_Low_40C_DataSet_2Post` | (not opened this round) | Skewed toward LOW discharge current | 40°C |

Only `Battery_Uniform_Distribution_Charge_Discharge` (its README) and
`RW_Skewed_High_Room_Temp` (its README AND one real `.mat` file,
`RW17.mat`) were actually opened this round, given the "small,
streamed" instruction — the other four are the same documented
format, not independently verified yet.

## Fields, confirmed by loading `RW17.mat` directly (not assumed from documentation)

`data.step` — 30,912 steps for this one battery alone. Each step:
`type` (`C`=charge, `D`=discharge, etc.), `comment` (plain-language,
e.g. `"charge (after random walk discharge)"`), `time`,
`relativeTime`, `date`, and per-sample arrays `voltage`, `current`,
`temperature` (162 samples for the one step inspected). Same core
voltage/current/temperature shape as the ARC dataset, at a finer,
per-step granularity, with real ambient-temperature variants (room
temp vs. 40°C) the ARC dataset doesn't have.

## What this adds beyond the ARC dataset

A REALISTIC, randomised load pattern (not a fixed charge/discharge
cycle) and an explicit high-temperature variant — both useful if a
later round wants the dying-battery fault's noise/load character to
look like real variable use rather than a clean lab cycle. Not
decided or built this round.

## Honest limits

- Only 2 of 6 variants' documentation read, only 1 `.mat` file
  actually loaded and inspected (`RW17.mat`) — the rest are assumed
  same format, not verified.
- Lab data at two fixed ambient temperatures, not flight telemetry.
- `MatlabSamplePlots.m` (NASA's own plotting script, kept alongside
  each variant's README) was not run this round.
