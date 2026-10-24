# Leash (drift-sense) simulated sensitivity test

**SIMULATED. Not real spacecraft data.** A controlled-conditions test
of the leash mechanism itself (SPEC.md's "Leash — drift sense
(stack-wide)" section), built because
[`real_data_tests/opssat_ad/`](../../real_data_tests/opssat_ad/)'s own
fragments turned out too short and spike-shaped to exercise sustained
drift at all — its leash scorecard registers zero pulls anywhere.
This test answers a different, narrower question: given a drift of a
known size, planted on purpose, does the mechanism built in
`run_opssat_ad_test.py` actually catch it, and how fast? It says
nothing about whether real spacecraft drift looks like these planted
shapes. The real long-duration test is ESA-ADB, later.

## How it works

- Normal wobble is built from real behaviour: consecutive-sample
  deltas are bootstrap-resampled from real OPSSAT-AD nominal training
  data (one real channel at a time, 1-second-sampled fragments only),
  de-meaned so a clean stretch has no drift of its own by
  construction.
- Two channels: CADC0872 (magnetometer) and CADC0894 (photodiode) —
  the only photodiode channel that has any 1-second-sampled data at
  all.
- Leash limits (soft/hard) are derived from pure-noise chunks, before
  any drift is planted, using the exact same `derive_leash_limits()`
  the real OPS-SAT test uses. A fixed derivation seed (0), separate
  from every scenario seed.
- Planted drifts are sized as fixed multiples of those already-derived
  limits: obvious (10x), moderate (2x), very slow (1.5x soft), tiny
  (0.5x soft — expected to go uncaught), and one that ramps up then
  returns to normal on its own.
- One ~2-hour (7,200s), 1Hz timeline per channel per seed. Five fixed
  seeds, reported individually and totalled. Nothing is tuned after
  looking at results.

## Running it

Needs `real_data_tests/opssat_ad/data/segments.csv` to already exist
(its noise source) — run that folder's download script first if not:

    python -m real_data_tests.opssat_ad.download_opssat_ad
    python -m simulated_tests.leash_drift.run_leash_drift_test

## Honest limits

- Soft and hard limits came out very close together for both channels
  (the nominal extreme-slope distribution's 95th and 99th percentiles
  are tight). As a result, the "very slow" case (1.5x the soft limit)
  also exceeded the hard limit in every seed — nothing in this run
  was caught at "soft" only. Testing the soft/hard distinction
  specifically would need a multiple chosen closer to 1x soft and
  comfortably below hard.
- This only tests the leash mechanism's sensitivity to the shapes
  planted here (steady ramps, one that reverses). Real drift may not
  look like a clean linear ramp.
- Context-gating isn't tested here either — there's no second agent
  in this simulation to report an expected cause.
