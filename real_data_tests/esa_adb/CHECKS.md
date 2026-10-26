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

**Yes, for most of it.** Of the 17 Mission1 Anomaly events STRICT's
level sense missed (40 total, 23 caught — matching RESULTS.md's
figure exactly, confirming this check lines up with the real scoring),
**13 (76%) were already latched FAULT on a confirmed FALSE alarm**
— not a different real labelled event — the moment the anomaly's own
window opened. Checked directly, not inferred: for every one of those
13, `latch_origin_label` is `None`, meaning the crossing that caused
the pre-existing latch itself fell outside every labelled window.

A bug was caught and fixed before trusting this number — see the
commit history and `check_masking.py`'s module docstring. The first
version of this check compared whether a FAULT latch merely
*overlapped* an anomaly's grace window, not whether the *transition*
into FAULT landed inside it (the real scoring's own definition). That
looser check silently hid the exact effect being measured here. Fixed,
re-run from scratch; the number above is from the corrected run.

| Channel | Anomaly events | Missed | Missed, already latched on a false alarm |
|---|---|---|---|
| channel_43 | 17 | 7 | 6 |
| channel_45 | 17 | 6 | 6 |
| channel_39 | 2 | 2 | 0 |
| channel_36 | 2 | 2 | 1 |
| channel_62/63/70/75 | 2 (combined) | 0 | — |
| **Total** | **40** | **17** | **13** |

**The masking is concentrated almost entirely in channel_43 and
channel_45** — 12 of their combined 13 misses are explained by a
pre-existing false latch; only 1 of their misses is a clean miss with
no latch involved. channel_39's and channel_36's misses are the
opposite pattern — only 1 of their combined 4 misses involves a false
latch; the other 3 were simply never caught at all, latch or no latch.

Looking at WHEN each false latch began (not just that one existed):
for nearly every one of channel_43/45's masked events, the false
latch began in the first few hours of THAT SAME CALENDAR DAY — e.g.
channel_43's 2012-09-19 anomaly at 13:42 sat behind a false latch that
began at 00:32 that same day. This fits the picture from RESULTS.md
and `CHECKS.md` 2a above: these two channels drifted enough, relative
to their own tightly-derived STRICT thresholds, that they re-fault
almost every single day shortly after the daily clear — so by the
time a real anomaly happens later that day, the channel is routinely
already (falsely) latched, and the transition-based scorer has
nothing new to catch. The masking hypothesis isn't just plausible
here; it's the dominant explanation for why these two channels'
Anomaly catch rate is as low as it is.
