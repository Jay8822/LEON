# Small Satellite Power Simulation (BP930 battery packs) — profile

Item 4b of the 26 October 2026 round (`Ccode update.txt`), the part
of it NOT on hold. **Look only — downloaded and profiled, no
scoring/testing code built this round.**

## The other half of item 4b: on hold, not attempted

Item 4b named two datasets. The **NASA Li-ion Battery Aging
Datasets** are **explicitly skipped this round** — Jay put the
battery dataset on hold earlier this session after the simulated
craft's own build hit a real access obstacle (DASHlink/c3.nasa.gov
timed out, data.nasa.gov's catalog page had no working direct link,
IEEE DataPort/Kaggle both require an account). Confirmed again this
round, same host, same result — see `real_data_tests/adapt/`'s
profile for the detail (ADAPT's own primary files are on the exact
same unreachable DASHlink host). Not re-attempted, no account
created, per that standing instruction.

The **Small Satellite Power Simulation** dataset below is genuinely
different — hosted directly on `data.nasa.gov` (not DASHlink) and
reachable — so it was downloaded and profiled.

## What it is

Two BP930 battery packs (PK31, PK35), each cycled on a MACCOR battery
test system through a simulated small-satellite loading profile — a
real, continuous charge/discharge/rest cycle, not an ageing-to-failure
study. Both packs start at roughly 8.35 V (the dataset's own
documentation says ~100% state of charge). Cite: Cameron, Kulkarni,
Guarneros, Goebel, Poll, "A Battery Certification Testbed for Small
Satellite Missions," AUTOTESTCON 2015.

## Format, confirmed by loading the actual files (not just the catalog description)

Two MATLAB `.mat` files (`PK31.mat`, 4.59 MB; `PK35.mat`, 374 KB),
each a single struct with fields `name`, `channel`, `procedure`,
`description`, `mode`, `step`, `modeIndices`. `step` is the real
data: an array of records, each with `index`, `step`, `comment`,
`type`, `cycle`, `time`, `relativeTime`, `voltage`, `current`,
`temperature`, `date`, `capacity`, `energy`.

PK31 has **1,516 step records**, spanning `time` 0 to 95,496.77
seconds (≈ 26.5 hours) at roughly 1-second sampling within each step.
`type` is one of `R` (rest), `D` (discharge), `C` (charge) —
confirmed directly: step 0 is a 61-second rest at ~8.355 V with zero
current; step 1 begins a discharge at ~8.342 V, ~0.05 A; by step
1515 (the last), voltage has risen to ~8.48–8.49 V during a charge,
with current around −0.15 A (sign convention: negative = charging).
Dates in the file run from 5/3/2016 to 5/4/2016.

**Honest gap, confirmed by inspection, not assumed from the catalog
description:** every `temperature` value sampled (across steps 0, 1,
2, 500, and 1515) reads exactly `0` — this channel does not appear to
have been populated for this profiling run, or temperature wasn't
actually measured/logged despite the field existing in the record
schema. Not independently confirmed for every one of the 1,516 steps,
or for `PK35.mat` — a closer check before any real use of this field
would be needed.

## Honest limits

- No fault/anomaly labels — this is a single continuous nominal
  cycling run, not a labelled-degradation dataset like the Li-ion
  Aging datasets this item originally also asked for (on hold).
- Only two packs, one run each — far less data than ESA-ADB/OPS-SAT,
  and not enough on its own to derive a real "normal noise" blueprint
  entry the way `simulated_tests/leash_drift/` bootstraps from OPS-SAT.
- `temperature` appears unpopulated (see above) — if a real test ever
  wants temperature alongside voltage/current, this dataset likely
  can't supply it.

## What this means for later rounds (not decided now)

Real battery voltage/current behaviour under a real satellite-style
load profile — useful as a REALISTIC NOISE SOURCE (the same role
OPS-SAT/ESA-ADB fragments play for `simulated_tests/leash_drift/`),
not as a labelled-fault test. Could plausibly stand in for the
simulated craft's battery_voltage/battery_current sensors if the
NASA Li-ion dataset stays unreachable — a real, reachable, if
smaller, alternative. Not decided or built this round.
