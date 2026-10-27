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
>
> **SECOND KNOWN GAP, FOUND THE SAME WAY:** Communication Gap rows
> were never actually dropped from test scoring — only from training
> derivation — despite the method always calling for them to be
> dropped entirely, train and test alike. The first run fed them
> through GracieAgent and scored "Communication Gap" as a real
> category. Mission1 has only 4 gap events total, so the likely
> effect on the figures below is small, but it was never checked
> before now. Fixed for the follow-up run; not editing these figures.

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

## What wasn't done (first run)

- No breakdown of which sense (level, jump, leash) produced each catch
  or each false alarm — see the follow-up run below, which added
  this.
- Jump's cross-check and leash's context-gating — still not built in
  `agents/gracie.py`, so not tested here regardless of what this
  dataset offers.
- No long-term drift/ageing measurement — see `DRIFT.md`, added
  alongside the follow-up run below.
- Results are the raw JSON in `results/` (committed alongside this
  file) plus this write-up — no further analysis beyond what's above.

---

## Follow-up run (per-sense breakdown, daily-clear fix, Communication
## Gap fix)

Same 16 channels, same cut-off dates, same settings. Re-run after
fixing both known gaps above and the daily `clear_fault()` stopwatch
issue (now `reset_leash_timer=False` — the latch clears every day,
the leash's pull-duration clock does not). Zero failures. Results in
`results/ESA-Mission{1,2}.json` (overwritten; the numbers above are
the first run's, kept in git history for reference).

### What each sense actually did (totals across all 8 channels per mission)

Mission1, STRICT — raw event counts: level=2,356, jump=3,137,127,
**leash=0**. LOOSE — level=288, jump=3,136,455, **leash=0**.
Mission2, STRICT — level=233, jump=16,506, **leash=0**. LOOSE —
level=134, jump=10,497, **leash=0**.

**Leash never fired once, in either mission, either setting, across
all 16 channels.** Confirmed, not just suspected as in the first run
(where `false_warning=0` was a hint but leash's contribution wasn't
actually isolated). The daily-clear fix changes nothing here because
there was never a pull for it to protect in the first place — same
story as OPSSAT-AD's leash result. The 1-hour window / 6-hour soft /
24-hour hard settings (test-fixture choices, not derived from this
data) simply don't match whatever real sustained drift exists in
these 16 channels, if any.

**Jump fired an enormous number of times — millions of individual
samples — which looked alarming until checked closely.** For
`channel_75` (one of the heaviest contributors), I compared the
per-day peak jump-rate distribution between training and test
directly: training and test medians/95th/99th percentiles are nearly
identical, and only 2.9% of test days exceed the training 95th
percentile — close to the ~5% you'd expect if nothing had changed.
**This is not a train/test mismatch.** What's actually happening: on
the small fraction of days that do exceed the threshold, the elevated
rate looks sustained through much of that day rather than a single
spike — so one "bad day" contributes hundreds or thousands of
individual sample-level jump events, not one. Scoring at the sample
level (every reading checked against the limit) makes a handful of
genuinely unusual days look like a constant storm. A per-day or
per-episode count, the way OPSSAT-AD's test was built, would likely
tell a much calmer story. Not fixed in this pass — flagging it as a
real scoring-granularity question for next time, the same way the
jump-field gap and the Communication Gap gap were flagged rather than
quietly patched.

### Catch rates by sense (Mission1, STRICT; Anomaly category, 40 events)

| Sense | Caught (logged or flagged) | Caught (flagged) |
|---|---|---|
| level | 23/40 | 23/40 |
| jump  | 32/40 | 0/40 |
| leash | 0/40  | 0/40 |
| any   | 25/40 | 23/40 |

Level is the only sense that ever reaches "flagged" here — matches
design (level→FAULT directly, jump→WARNING only, leash never fired).
Jump logged more Anomaly events (32/40) than it flagged anything, by
definition — it's a much busier, much lower-severity signal than
level. Full per-cause tables for both missions and settings are in
`results/ESA-Mission{1,2}.json`.

### The "LOOSE beats STRICT" finding stands, unchanged

Level's own numbers didn't change between runs (level's logic and
derivation weren't touched) — STRICT still catches fewer Mission1
Anomalies by level (23/40) than LOOSE (32/40), and STRICT's level
false-flag count is still concentrated in `channel_43`/`channel_45`.
The masking hypothesis from the first run (a channel already falsely
latched FAULT hides a later genuine anomaly from this transition-based
scorer) is unchanged by this round's fixes and still unconfirmed —
see `ASSUMPTIONS.md` A76.

### The long-term-drift explanation for the false-fault volume is weaker than first thought

`DRIFT.md` (Plan A, built alongside this) measured real year-to-year
drift for every monitored channel in both missions. **It doesn't
strongly support the original hypothesis.** `channel_43`'s test
period sits only 0.55 training-IQRs from its training median — modest
— and `channel_45` doesn't appear near the top of either drift
ranking at all. Reporting this plainly rather than forcing the
earlier story to fit: median-level long-term drift, as actually
measured, isn't the main explanation for those two channels' false
alarms. See `DRIFT.md` for the full measurement.

## What wasn't done (follow-up run)

- Jump and leash's event counts weren't re-expressed per-day or
  per-episode, which the "enormous jump count" finding above suggests
  would be far more informative than the raw per-sample count used
  here.
- Jump's cross-check and leash's context-gating — still not built.

## v2 rerun (stand-in linked_channels, noise-filter measurement,
## context-checking x3 windows, per-reading + per-episode counts)

Same 16 channels, same cut-off dates, same STRICT/LOOSE settings,
same daily `clear_fault(reset_leash_timer=False)`. Four additions
layered on top of the follow-up run, all built and run per Jay's
26 October 2026 four-step round. Results in
`results/ESA-Mission{1,2}-v2.json`. Zero failures, after two real
infrastructure problems on this run (not scoring bugs) were caught
and fixed first — see `Ccode update.txt`'s history and the commit
log: `check_pretrip.py`'s MemoryError (58 channels held in memory at
once), and this script's own unexplained crash partway through
Mission2, fixed by converting `values` to a numpy array and proved
identical to the pre-fix result on `channel_78` before trusting it.

### (d) Per-reading vs per-episode: the gap flagged above, closed

**Confirmed, and it's a big effect on Mission1.** Collapsing jump's
false counts into episodes (a run of same-cause events with no gap
longer than 3x that channel's own median sample interval) instead of
counting every sample:

| Mission | Setting | Jump false count, per-reading | Jump false count, per-episode | Reduction |
|---|---|---|---|---|
| Mission1 | STRICT | 3,098,112 | 662,008 | 4.7x |
| Mission1 | LOOSE | 3,097,785 | 661,731 | 4.7x |
| Mission2 | STRICT | 14,317 | 14,241 | ~1x (negligible) |
| Mission2 | LOOSE | 8,962 | 8,962 | none |

Exactly what the follow-up run's own write-up predicted: "a handful of
genuinely unusual days look like a constant storm" at the per-sample
level. Mission1's heaviest jump contributors really are a small number
of sustained bad stretches, not millions of independent events — once
collapsed, the picture is roughly 5x calmer. Mission2 doesn't show the
same effect at all, meaning its jump false alarms genuinely are many
separate, short events, not a few long storms — a real difference
between the two missions' channels, not a scoring artefact either way.
Level's counts are unchanged by this collapse (level already latches
once per crossing, so per-reading and per-episode are nearly
identical by construction — see the small table below). Leash stays
at zero, as always.

### (c) Context-checking (GRACIE's new `expected_causes` input)

**A real but modest effect, and it doesn't touch genuine catches.**
Training-only command/event correlation (`learn_context.py`) feeds
GRACIE a per-sample "this crossing has an expected cause" flag; per
SPEC.md, that demotes a level crossing from FLAGGED to LOGGED, never
downgrading an existing FAULT latch.

| Mission | Setting | Window | Level false, FLAGGED | Level false, LOGGED (demoted) |
|---|---|---|---|---|
| Mission1 | STRICT | 1 min | 2,291 | 2 |
| Mission1 | STRICT | 10 min | 2,288 | 19 |
| Mission1 | STRICT | 1 hour | 2,274 | 85 |
| Mission2 | STRICT | 1 min | 190 | 0 |
| Mission2 | STRICT | 10 min | 192 | 31 |
| Mission2 | STRICT | 1 hour | 180 | 18 |

Widening the window demotes more false alarms (as expected — a longer
look-back catches more of them), but the effect stays small in
absolute terms: at most ~4% of Mission1's false level alarms and ~15%
of Mission2's, even at the widest (1-hour) window. **Anomaly catch
rate is completely unchanged by this** (Mission1 STRICT level:
23/40 caught, flagged or logged, identical at every window) — context-
checking only ever softens false alarms here, it never costs or gains
a real catch. Whether that's because the test channels' real anomalies
never coincide with a command/event in the correlation list, or
because the correlation itself is too narrow, isn't established by
this pass.

### (b) Noise-filter instrumentation (measurement only, not wired into scoring)

89.2% of Mission1's sample-to-sample deltas and 91.7% of Mission2's
fall within the learned stand-in's own noise band (`big_change_cutoff`
from `stand_in_blueprint.py`). Built and measured as planned, but as
the script's own module docstring says plainly: this does **not**
alter anything fed to GracieAgent in this pass. `jump_limit` is
already a 95th/99th-percentile *extreme* of day-level rate, so it
already excludes ordinary noise by construction — the enormous jump
count above comes from sustained elevated-but-still-above-jump_limit
days (see "(d)" above), not borderline noise, so filtering "normal
noise" out of jump detection wouldn't touch that finding either way.
Reported here as a measurement, not expanded into a scoring change
that was never approved.

### (a) `linked_channels` (stand-in blueprint's jitter-together links)

**Null result, as predicted and as already flagged honestly in the
script's own module docstring before this run.** Wired into every
`ChannelRule` exactly like any other rule-book value, for every
channel the stand-in found a 1-minute jitter-together link for
(Mission1 only: channel_39/43/45/62/63/64/70/75 area — see
`results/ESA-Mission1-stand-in.json`). `linked_channels` only matters
to leash's settling exception, and leash has never fired once in
ESA-ADB, in any pass, any mission, any setting. Built and wired
correctly, confirmed to make no difference to any scored number —
reported as a null result, not silently dropped.

## What wasn't done (v2 rerun)

- The noise filter remains a measurement, not a live filter — SPEC.md
  says a real noise filter needs a real blueprint (see Blueprint),
  which this dataset doesn't have; wiring it into scoring here would
  mean testing against a stand-in pretending to be a blueprint, not
  GRACIE's real design.
- Whether context-checking's small effect is a ceiling (the
  correlation method genuinely has little more to find here) or a
  floor (a richer blueprint/command list would find more) isn't
  established by this pass.
- Jump's cross-check and leash's context-gating from the earlier
  follow-up run — still not built.
- Still a first test, not a validation.
