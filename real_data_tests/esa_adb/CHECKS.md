# ESA-ADB quick checks (Step 2 of the 26 October 2026 four-step round)

Two targeted checks on existing ESA-ADB data, both look-only (no
`GracieAgent` in 2a; a replay of the real agent in 2b, but reporting
facts about existing labelled events, not a rescore). See
`check_noise.py` and `check_masking.py`.

## 2a — Did channel_43 / channel_45 get noisier, or drift?

Compared training vs. test periods on **peaks and spread**, not the
average: daily maximum/minimum, high/low percentiles (95th/5th,
99th/1st), and day-to-day spread (IQR) of those daily peaks. Labelled
rows and Communication Gap excluded, same as every other "normal
behaviour" measurement in this project.

### channel_43

| Stat | Train | Test | Change |
|---|---|---|---|
| median | 0.7719 | 0.7672 | -0.0047 |
| p95 | 0.7798 | 0.7751 | -0.0047 |
| p5 | 0.7640 | 0.7592 | -0.0048 |
| daily max, median | 0.7814 | 0.7766 | -0.0048 |
| daily min, median | 0.7608 | 0.7561 | -0.0047 |
| daily max, IQR (spread) | 0.001583 | 0.002374 | +50% |
| daily min, IQR (spread) | 0.003166 | 0.003164 | ~0% |

### channel_45

| Stat | Train | Test | Change |
|---|---|---|---|
| median | 0.8126 | 0.8092 | -0.0034 |
| p95 | 0.8219 | 0.8186 | -0.0033 |
| p5 | 0.8041 | 0.8007 | -0.0034 |
| daily max, median | 0.8236 | 0.8202 | -0.0034 |
| daily min, median | 0.7990 | 0.7974 | -0.0016 |
| daily max, IQR (spread) | 0.0008487 | 0.001695 | +100% |
| daily min, IQR (spread) | 0.001695 | 0.001696 | ~0% |

**Plain answer: drift, not noise.** For both channels, the median, the
5th/95th percentiles, and the daily max/min medians all shifted down
by almost exactly the same amount — the whole distribution moved as a
block, rather than the peaks spreading out while the middle stayed put.
That's the signature of a level shift, not of the channel getting
jumpier. (There's a secondary, smaller effect too: the spread of daily
maxima did widen — +50% on channel_43, +100% on channel_45 — so the
*peaks* did get a bit more variable on top of the shift, but it's a
second-order effect next to the uniform downward move.)

### Reconciling this with DRIFT.md's "modest drift" finding

This looks like it should contradict DRIFT.md, which measured the same
two channels' test-vs-training distance as modest (channel_43: -0.55
training IQRs; channel_45 not near the top of either ranking). It
doesn't — it resolves it. DRIFT.md's "IQR" is the spread of *all*
nominal readings pooled together, which is wide (a channel wobbles a
fair amount sample to sample within any given day). But the STRICT/
LOOSE level thresholds in RESULTS.md are derived from a **much
tighter** distribution: the 95th/5th percentile of each day's own
*extreme* (`derive_rules()` in `run_esa_adb_test.py`), not of
individual readings. For channel_43, train `daily_min_iqr` is
0.003166 and `daily_max_iqr` is only 0.001583 — several times
tighter than the raw-reading spread DRIFT.md measured against.

So the same absolute shift (~0.0047-0.0048) is:
- **modest** against the wide, all-readings IQR DRIFT.md used (~0.55
  IQRs) — correctly reported as "not dramatic" there;
- **large** against the tight, day-extreme IQR the actual thresholds
  are built from (roughly 1.5-3x channel_43's day-extreme IQRs,
  depending which side; similarly large for channel_45's ~4x) —
  which is why STRICT's level thresholds, set from the training
  period's tight day-extreme distribution, get crossed constantly
  once the test period's whole distribution has quietly shifted past
  them.

Both findings stand; they were just measured on two different scales.
The false-fault volume on these two channels is consistent with real,
if modest-in-absolute-terms, drift — not a contradiction in this
project's own numbers, and not evidence that something else entirely
is going on. Reported here plainly, correcting the loose impression
DRIFT.md may have given on its own.

## 2b — Is the masking hypothesis (ASSUMPTIONS.md A76) real?

*(In progress — replaying the real GracieAgent against Mission1,
STRICT, is a near-full rerun of that setting and takes time. Findings
will be added here once it finishes; see `check_masking.py`.)*
