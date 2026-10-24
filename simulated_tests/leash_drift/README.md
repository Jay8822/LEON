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

Updated 2026-10-24: the leash was redefined from two slope-based
limits (soft/hard) to one slope limit plus two durations — soft/hard
came out almost identical as slopes on real data, so the original
version of this test couldn't show them working separately. This
version plants drifts of different *durations*, at the same
comfortable slope margin, to test that distinction directly.

- Normal wobble is built from real behaviour: consecutive-sample
  deltas are bootstrap-resampled from real OPSSAT-AD nominal training
  data (one real channel at a time, 1-second-sampled fragments only),
  de-meaned so a clean stretch has no drift of its own by
  construction.
- Two channels: CADC0872 (magnetometer) and CADC0894 (photodiode) —
  the only photodiode channel that has any 1-second-sampled data at
  all.
- One slope limit per channel, derived from pure-noise chunks before
  any drift is planted, using the exact same `derive_leash_limits()`
  the real OPS-SAT test uses. A fixed derivation seed (0), separate
  from every scenario seed.
- Every catchable planted drift uses the same comfortable margin (5x
  the limit) — what varies is duration: below_soft (too brief for
  even soft), soft_only (past soft, short of hard, by holding at its
  new level forever), settles_back (past soft, then subsides back to
  normal before hard — the key case for "give it a chance to settle,
  escalate only if it doesn't go away on its own"), reaches_hard (past
  hard), tiny (0.5x the limit — below it entirely, expected uncaught
  regardless of duration), and returns (ramps past hard, then back to
  normal). Durations were chosen while building this test fixture
  (checking they land clearly on one side of the 60s/150s boundary),
  not by tuning against any scored result.
- One ~2-hour (7,200s), 1Hz timeline per channel per seed. Five fixed
  seeds, reported individually and totalled. Nothing is tuned after
  looking at results.

## Running it

Needs `real_data_tests/opssat_ad/data/segments.csv` to already exist
(its noise source) — run that folder's download script first if not:

    python -m real_data_tests.opssat_ad.download_opssat_ad
    python -m simulated_tests.leash_drift.run_leash_drift_test

## Honest limits

- This only tests the leash mechanism's sensitivity to the shapes
  planted here (steady ramps at a fixed 5x margin, one that reverses).
  Real drift may not ramp this cleanly or sit this comfortably above
  the limit.
- Context-gating isn't tested here either — there's no second agent
  in this simulation to report an expected cause.
