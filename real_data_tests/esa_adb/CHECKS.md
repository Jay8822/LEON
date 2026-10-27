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

## 2c — What happens just before each false trip?

For every false FAULT transition on channel_43 (930) and channel_45
(967) — "false" meaning outside every labelled window, same
definition RESULTS.md's `false_counts` uses — checked what fired or
moved in the preceding 1 minute / 10 minutes / 1 hour, and when in
the day they happen. See `check_pretrip.py`.

### Telecommands: barely any

| Window | channel_43 trips with ANY telecommand | channel_45 trips with ANY telecommand |
|---|---|---|
| 1 min | 9 / 930 (1%) | 16 / 967 (2%) |
| 10 min | 53 / 930 (6%) | 70 / 967 (7%) |
| 1 hour | 220 / 930 (24%) | 248 / 967 (26%) |

Even at the 1-hour window, where roughly a quarter of trips have
*some* telecommand in the preceding hour (a wide window, on a craft
that fires commands often), one telecommand accounts for most of
that: telecommand_493 (142 of channel_43's 220 hourly hits, 162 of
channel_45's 248). That's the same telecommand `learn_context.py`
already flagged as firing so often in training that clearing the
statistical bar doesn't mean much on its own ("weaker in character",
see its module docstring). **Plain answer: these trips are not
commanded** — at the window that actually matters for "did something
just happen," essentially nothing fired.

### Other channels moving: common, but the most frequent one isn't the one the rigorous check trusts

| Window | channel_43 trips with another channel moving | channel_45 trips with another channel moving |
|---|---|---|
| 1 min | 445 / 930 (48%) | 490 / 967 (51%) |
| 10 min | 789 / 930 (85%) | 831 / 967 (86%) |
| 1 hour | 895 / 930 (96%) | 930 / 967 (96%) |

channel_76 is the single most common companion at every window for
both target channels (314/930 and 358/967 even within 1 minute). But
`stand_in_blueprint.py`'s jitter-together check — built the rigorous
way, against a random control, same method `learn_context.py` uses
for commands — does **not** flag channel_76 as linked to channel_43
or channel_45 at any window. It flags channel_61/62/63/64 instead
(1-minute window only), and none of those four even make channel_43
or channel_45's top-10 raw co-occurrence list. The likely explanation:
channel_76 is itself a frequently, independently triggering channel,
so it shows up near almost anything by sheer base rate, not because
it's functionally tied to channel_43/45. **Plain answer: mostly
coincidental, not a demonstrated link** — the one relationship that
passes the stricter test is a minor player in the raw numbers, and
the dominant raw co-mover doesn't pass the stricter test.

### Time of day: a real pattern, and it's the same one 2b already found

| Time of day | channel_43 trips | channel_45 trips |
|---|---|---|
| 00:00-04:00 | 426 (46%) | 527 (55%) |
| 04:00-12:00 | 389 (42%) | 338 (35%) |
| 12:00-18:00 | 92 (10%) | 84 (9%) |
| 18:00-24:00 | 23 (2%) | 18 (2%) |

Both channels' false trips are heavily front-loaded into the first
half of the day and fall away sharply by evening. But they're not
sitting right on top of the daily `clear_fault()` itself — only 2% of
each channel's trips (21/930, 24/967) land within 5 minutes of it; the
median trip happens 4.6 hours (channel_43) / 3.5 hours (channel_45)
after that day's clear. So the pattern isn't "re-trips the instant the
latch clears" — it's "re-trips sometime in the first several hours of
the day, tailing off as the day goes on." That's consistent with, and
sharpens, 2b's own example (channel_43's false latch on 2012-09-19
began at 00:32, a few hours after midnight) — the same drift-vs-
tightly-derived-threshold story from 2a, now shown to have a
time-of-day shape rather than firing at any random moment.

**Taken together, plain answer to "tied to other activity, or from
nowhere?": neither, really.** They're not commanded, and the channel
most often moving alongside them doesn't hold up as a genuine link
once checked properly. But they're not random either — they have a
real, reproducible time-of-day shape, concentrated in the first half
of each day. That shape is best explained by the same cause 2a/2b
already identified (drift past a tightly-derived threshold,
compounding over each day since the last clear), not by some separate
trigger this check turned up.

### Follow-up: does the time-of-day pattern survive counting every raw crossing, not just the first per day?

**No — it's substantially a test-method artefact, not a craft
behaviour.** The front-loaded pattern above is counted in FAULT
*transitions*: once a channel latches early in the day (right after
the daily `clear_fault()` gives it a fresh chance to), it mostly stays
latched, so the many further over-threshold readings later that day
never register as new transitions. Counting instead every single raw
sample that sits over the STRICT line — whatever the latch state,
labelled periods excluded the same way as above — gives a very
different picture:

| Time of day | channel_43 (8,439 false samples) | channel_45 (10,325 false samples) | Duration-proportional baseline |
|---|---|---|---|
| 00:00-04:00 | 15% | 15% | 17% |
| 04:00-12:00 | 34% | 34% | 33% |
| 12:00-18:00 | 25% | 25% | 25% |
| 18:00-24:00 | 25% | 25% | 25% |

That's indistinguishable from flat — within a couple of points of what
you'd get if false readings were spread uniformly across the day with
no time-of-day effect at all (the "baseline" column is just each
window's share of the 24 hours). **The channel really is over
threshold fairly uniformly through the day; it's the combination of
daily latch-clearing and transition-only counting that made it look
front-loaded.** This doesn't undo 2a/2b's drift finding — the channel
is still falsely over threshold because of drift relative to its
tightly-derived limit, for the same reasons already established — it
just means "when in the day" isn't actually part of that story. Noted
here plainly rather than left standing uncorrected.
