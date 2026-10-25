# ESA-ADB test results

**First test against real spacecraft data. Not a validation.** Run
2026-10-24/25 through the real `GracieAgent` (`agents/gracie.py`), via
`run_esa_adb_test.py`. See that script's module docstring and this
folder's `README.md` for the full method; this file is the write-up
of what actually happened when it ran.

> **KNOWN GAP IN THE FIGURES BELOW, FOUND AFTER THIS RUN:** this
> first pass scored severity by reading a field that only reflects
> GRACIE's LEVEL and LEASH senses — JUMP's contribution lives in a
> separate aggregate field that this scoring never read. So jump's
> effect on every catch and false-alarm count below is **missing, not
> zero**. A follow-up run that tags each catch by sense (level, jump,
> leash) is planned; the numbers below will be updated once it's run.
> Not editing the figures now — recording the gap plainly instead.

## Run

## Run

All 16 channels (8 per mission), both settings (STRICT, LOOSE), zero
failures, zero skipped channels. Total runtime ~5.07 hours (Mission1
11,850s, Mission2 6,394s) — one channel at a time, checkpointed after
each, never more than one channel's full series in memory.

## Chosen channels

Picked by the fixed, subsystem-stratified rule in `select_channels()`
(seed 20261025) — no cherry-picking:

- **Mission1**: `channel_62`, `channel_75`, `channel_43`, `channel_39`,
  `channel_63`, `channel_70`, `channel_45`, `channel_36`
- **Mission2**: `channel_22`, `channel_96`, `channel_78`, `channel_91`,
  `channel_21`, `channel_98`, `channel_76`, `channel_88`

## Cut-off dates (shared per mission, 70% of that mission's span)

- Mission1: **2009-10-19 19:11:59** (span: 2000-01-01 to 2013-12-31)
- Mission2: **2002-06-12 21:35:54** (span: 2000-01-01 to 2003-06-30)

## Scorecards

"Caught" means a transition into FAULT landed inside the labelled
window (± 1 hour grace). Every catch in this run, in every channel
and both settings, was a FAULT — none were WARNING-only. That's
recorded honestly, not smoothed over: this pass didn't break results
down by which sense (level, jump, leash) produced each catch or false
alarm, so there's no way to say from this data alone whether leash or
jump contributed anything at all. See "What wasn't done" below.

### Mission1 (40 Anomaly events, 106 Rare Event events in the test period)

| Setting | Anomaly caught | Rare Event caught | false_warning | false_fault |
|---|---|---|---|---|
| STRICT | 23/40 (57.5%) | 28/106 (26.4%) | 0 | 2,292 |
| LOOSE  | 32/40 (80.0%) | 17/106 (16.0%) | 0 | 227 |

### Mission2 (3 Anomaly events, 358 Rare Event events in the test period)

| Setting | Anomaly caught | Rare Event caught | false_warning | false_fault |
|---|---|---|---|---|
| STRICT | 0/3 (0%) | 43/358 (12.0%) | 0 | 190 |
| LOOSE  | 0/3 (0%) | 32/358 (8.9%) | 0 | 104 |

## Honest findings

**LOOSE caught more Mission1 Anomalies than STRICT (32 vs. 23) — the
opposite of what "stricter means more sensitive" would predict.**
Looking at the per-channel breakdown, this is concentrated in two
channels specifically — `channel_43` and `channel_45` — which also
produced almost all of STRICT's false-alarm volume (930 + 967 =
1,897 of Mission1's 2,292 `false_fault` total). Working explanation,
not fully confirmed: STRICT's tighter level bound on these two
channels fires so often on ordinary later-mission drift that the
channel is often already (wrongly) latched FAULT by the time a
genuine anomaly's window begins. Scoring only looks for a *new*
transition landing inside the labelled window, so an anomaly that
starts while the channel is already falsely latched produces no new
transition to find — LOOSE, firing far less often, has a cleaner
timeline and catches the real event instead. If this is right, it
means STRICT's extra false alarms aren't just noise alongside its
catches — they're actively costing it real catches. Worth confirming
properly (see Job 4, Plan B) rather than trusting this number as is.

**The false-fault volume looks like long-term drift, not anomalies.**
Level thresholds were derived from only the first 70% of each
recording (14 years for Mission1, 3.5 years for Mission2). Components
age and drift over a mission that long — committed to writing as its
own open question before this run (`ASSUMPTIONS.md` A74-A76, added
alongside this) — so thresholds set early in the mission should be
expected not to hold at the back end, independent of anything actually
going wrong. Most of the false-fault count looks consistent with
exactly that, not with GRACIE being "wrong" about real anomalies.

**Anomaly and Rare Event are not separable by level/jump/leash — as
predicted before this ran, not discovered after the fact.** Neither
setting nor mission shows a clean split between the two categories;
catch rates range 12-80% depending on setting/mission/category with
no consistent pattern favouring one over the other. GRACIE's current
senses have no expected-cause signal (that's exactly the gap jump's
cross-check and leash's context-gating would fill, neither built
yet), so they have no way to tell a Rare Event apart from a real
Anomaly, and the results don't show them being told apart either.

**Mission2's Anomaly sample is too small to read anything into the
0/3 figure.** Only 3 Anomaly-category events fall inside Mission2's
test period across all 8 selected channels combined (Mission2 only
has 31 Anomaly events in the entire mission, spread across 47
monitored channels, and is heavily skewed toward Rare Events — 613 of
them — to begin with). 0/3 is reported honestly, not stretched into a
conclusion either way.

**The daily `clear_fault()` stand-in for sign-off has a real side
effect, found while building the test, not discovered afterwards.**
It resets the leash pull-duration clock (and its soft/hard
edge-detectors) along with the latch — it does not touch the windowed-
slope sample history. So a drift that would only cross the 24-hour
hard duration by straddling a day boundary could never be scored as
reaching hard under this methodology. `GracieAgent.clear_fault()`
was not changed to behave differently — that would be an agent
behaviour change, out of scope — so this stands as a known limit of
this run's method, not something quietly worked around. See Job 4,
Plan B for what a smaller, targeted fix might look like.

## What wasn't done

- No breakdown of which sense (level, jump, leash) produced each catch
  or each false alarm — unlike OPSSAT-AD's test, which did split this
  out. Without it, the "LOOSE beats STRICT" finding above stays a
  working hypothesis, not a confirmed explanation.
- Jump's cross-check and leash's context-gating — still not built in
  `agents/gracie.py`, so not tested here regardless of what this
  dataset offers.
- No long-term drift/ageing measurement — SPEC.md's new "Ageing"
  section (added alongside this write-up) describes what GRACIE
  *should* eventually do about exactly the drift this run's
  false-alarm volume points at; this run doesn't measure that drift
  directly. See Job 4, Plan A.
- Results are the raw JSON in `results/` (committed alongside this
  file) plus this write-up — no further analysis beyond what's above.
