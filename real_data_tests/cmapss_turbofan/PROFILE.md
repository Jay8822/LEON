# C-MAPSS Turbofan Engine Degradation Simulation — profile

Addendum to Item 4 of the 26 October 2026 round (`Ccode update.txt`).
**Look only — FD001 downloaded and profiled, no scoring/testing code
built this round.**

## THIS IS AN AIRCRAFT ENGINE SIMULATION, NOT A SPACECRAFT ONE

Stated here exactly as Jay's instruction required, and repeated
everywhere else this dataset is mentioned: C-MAPSS (Commercial
Modular Aero-Propulsion System Simulation) models a large commercial
**aircraft** turbofan, not a spacecraft thruster or power system. It
is a physics-based SIMULATION of engine degradation to failure, not
real flight telemetry. Cite: Saxena, A., Goebel, K. (2008), "Turbofan
Engine Degradation Simulation Data Set," NASA Ames Prognostics Data
Repository.

## A genuine access obstacle, same as ADAPT and the Li-ion battery dataset

NASA's own primary host for this (DASHlink / `c3.nasa.gov`) is
unreachable from this machine — confirmed again this round, same
host, same result as `real_data_tests/adapt/`'s profile. Per Jay's
own instruction, the live C-MAPSS SIMULATOR tool is separately known
to be unavailable from NASA directly; the pre-generated dataset
itself was the target here regardless, and it's the dataset (not the
simulator) that's blocked by the DASHlink outage.

**Fetched instead from a reachable mirror**, not NASA directly: a
public, non-gated Hugging Face dataset
(`SoyVitou/NASA-C-MAPSS-Turbofan-Engine`) that repackages the same
four FD00X sub-datasets as Parquet files. **Checked carefully before
trusting it**: a different candidate mirror found first (an S3
bucket linked from a GitHub project) turned out to be a 15.76 GB file
— that's **N-CMAPSS**, a different, much newer (2021) NASA dataset
with full continuous flight recordings, not the classic small FD001-4
set Jay described ("the ready-made dataset... in the repository").
Not downloaded — wrong dataset, caught before wasting disk/bandwidth
on it, not after. Licence on the Hugging Face mirror is listed only
as "other" (unspecified) — the underlying NASA data is a US
government work, but this specific repackaging's own licence is
unclear; prefer NASA's own files directly if DASHlink ever becomes
reachable again.

## Structure, confirmed by loading FD001 directly (not assumed from documentation)

`FD001_train.parquet` (535,186 bytes): **20,631 rows × 29 columns**,
**100 distinct engine units**, run-to-failure (max cycle count seen:
362). Columns, confirmed directly: `unit_id`, `cycle`, three
operating-condition settings (`setting_1/2/3`), 21 real-named sensor
channels matching the standard C-MAPSS schema (temperatures `T2`,
`T24`, `T30`, `T50`; pressures `P2`, `P15`, `P30`, `Ps30`; speeds
`Nf`, `Nc`, `NRf`, `NRc`; and `epr`, `phi`, `BPR`, `farB`, `htBleed`,
`Nf_dmd`, `PCNfR_dmd`, `W31`, `W32`), a `RUL` (Remaining Useful Life)
column — the run-to-failure ground truth this dataset is built
around — plus `dataset`/`split` labels from the mirror's own
repackaging. `FD001_test.parquet` (351,364 bytes) was also fetched
but not individually inspected beyond confirming its size matches
the mirror's own published size exactly.

FD001 specifically is the simplest of the four sub-datasets: ONE
operating condition (sea level), ONE fault mode (HPC — high-pressure
compressor — degradation). FD002-004 add more operating conditions
and/or a second fault mode (not fetched this round).

## Honest limits

- This mirror's Parquet files are NOT the original DASHlink `.txt`
  format — reformatted by a third party, not NASA. The column names
  and values matched the well-documented standard C-MAPSS schema
  exactly when checked, but the repackaging itself hasn't been
  independently audited against NASA's original files (which remain
  unreachable to compare against).
- Only FD001 fetched and inspected this round; FD002-004 follow the
  same URL pattern but weren't downloaded.
- Simulated degradation, not real hardware ageing — useful as a
  LABELLED run-to-failure structure to test an ageing/drift detector
  against a known RUL, but never a substitute for real spacecraft
  ageing behaviour, and never to be described as one.

## What this means for later rounds (not decided now)

A genuinely good candidate for testing SPEC.md's Ageing section
against a dataset that actually HAS a ground-truth remaining-useful-
life label (no real spacecraft dataset in this project has that) —
but it must stay clearly labelled as an aircraft-engine simulation
throughout, never conflated with spacecraft ageing. Any actual test
plan is a separate, later round, ambiguities first, same as every
other dataset decision this session.
