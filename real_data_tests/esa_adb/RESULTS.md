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

---

## Job 2: every other monitored channel (50 new Mission1, 39 new Mission2)

> **EVERY NUMBER IN THIS SECTION AND "PER-EVENT CATCH RATE" BELOW
> PREDATES GRACIE'S CLOCK-HEALTH RULE** (commit `e6053f7`, 6 November
> 2026). All 89 channels here have backward timestamp jumps on the
> same dates (a DST artifact, see `ASSUMPTIONS.md` A84) — 14 per
> Mission1 channel, 4 per Mission2 channel — that this scoring ran
> through unflagged. Under the new rule, every channel would also
> flag each of those jumps, and a flag latches the channel until the
> daily clear — so false-alarm counts would rise slightly, and a
> latch could mask a real crossing landing on one of those days. Not
> rerun yet, by decision: held until the next batch of GRACIE changes
> is done, then everything reruns once together — see "What wasn't
> done" below.

Same method as the v2 rerun above (same STRICT/LOOSE derivation, same
per-reading scoring, same three context-check windows, same daily
`clear_fault(reset_leash_timer=False)`), run on every monitored
channel **not** in the original 16: Mission1 has 58 monitored channels
(50 new), Mission2 has 47 (39 new). No design changes — reuses
`run_esa_adb_test_v2.py`'s scoring functions directly, driven by a
background queue job (`bg_jobs/queue/job2_esa_adb_all_channels.py`)
over several days and multiple stop/fix/restart cycles (a
logging/rotation performance fix partway through — see `Ccode
update.txt`'s history). Same cut-off dates as above. Zero failures,
zero skipped channels — all 89 monitored channels across both
missions are now scored.

Results in `results/ESA-Mission{1,2}-v2-allchannels.json` (new files —
the original 16 channels' own `results/ESA-Mission{1,2}-v2.json`
files are untouched). Measured compute time, summed per channel
(excludes queue downtime between restarts, so not directly comparable
to the single-pass runtimes above): Mission1 ~46.3h, Mission2 ~2.6h,
accumulated across several days, not one continuous sitting.

### Scorecards (per-reading; identical across all three context windows — see "Honest findings")

**Mission1** (50 channels; 247 Anomaly label-rows across 49 channels, 405 Rare Event label-rows across 44 channels):

| Setting | Anomaly, level flagged | Anomaly, any logged | Rare Event, level flagged | False level, flagged |
|---|---|---|---|---|
| STRICT | 83/247 (33.6%) | 111/247 (44.9%) | 74/405 (18.3%) | 7,710 |
| LOOSE  | 84/247 (34.0%) | 104/247 (42.1%) | 58/405 (14.3%) | 2,270 |

**Mission2** (39 channels; 14 Anomaly label-rows across 14 channels, 2,960 Rare Event label-rows across 38 channels):

| Setting | Anomaly, any sense | Rare Event, level flagged |
|---|---|---|
| STRICT | 0/14 (0%) | 1,588/2,960 (53.6%) |
| LOOSE  | 0/14 (0%) | 1,376/2,960 (46.5%) |

Full per-channel, per-sense, per-episode numbers are in the result
files — these are the headline rows asked for.

### Honest findings

**The original 16 channels flattered GRACIE — said plainly.** The
first run's level catch rate (23/40 = 57.5%, Mission1 STRICT) looked
respectable. Scored against the 50 channels nobody hand-picked for
this run, the same STRICT level sense catches 83/247 = 33.6%. The
original 8 Mission1 channels were chosen by a fixed,
subsystem-stratified rule, not cherry-picked for a good result — but
8 channels is a small, lucky-or-unlucky sample next to 50. The wider
run is the more trustworthy number, and it's meaningfully worse.

**Most of Mission1's 247 "Anomaly" label-rows are a handful of real
events, not 247 — counted directly against the raw labels, not
assumed.** ESA-ADB's `labels.csv` carries an event `ID` per row, and
the same ID recurs across every channel a multivariate/global event
touched (`anomaly_types.csv`'s own `Dimensionality`/`Locality`
columns name exactly this). Collapsing Mission1's 247 Anomaly rows by
that ID gives **34 distinct events** — one single event alone
accounts for 47 of the 50 scored channels' rows. Rare Event's 405
rows collapse to **19 distinct events**. Mission2 is the starkest
case: all 14 of its "Anomaly" rows (one per channel, 14 channels) are
**the same single event**, seen on every one of the 14 channels it
touched — and caught by GRACIE on none of them, in either setting.
That's one real, complete miss, not fourteen; worth stating
accurately rather than letting the channel-label-pair count imply
fourteen separate failures (one correction once the original 16 are
also counted — see "Per-event catch rate" below). Mission2's 2,960
Rare Event rows are **195 distinct events**. None of this changes any
catch/false-alarm number above — GRACIE scores each channel
independently, so those counts are correct as given — it changes how
the *label totals* should be read.

**LOOSE vs STRICT on the new channels: a wash on catches, a real win
on false alarms.** Level catches land within one event of each other
(83 vs 84 of 247), but LOOSE cuts false level-flagged faults 3.4x
(7,710 → 2,270). Unlike the original 16 (where LOOSE caught
substantially *more* Anomalies than STRICT, 32 vs 23 — see above),
here LOOSE isn't buying extra catches, just a much quieter false-alarm
line. 25 of the 50 channels have zero false level faults under LOOSE
at all; `channel_76` alone accounts for 1,187 of LOOSE's 2,270 (52.3%,
essentially half) — one channel's ordinary behaviour, not a
spread-out problem. STRICT's "any logged" number (111) beats LOOSE's
(104) — jump logs more under the tighter setting, as expected — but
neither setting's level-flagged catch rate is the clear win LOOSE was
on the first 16.

**Leash: still zero, now checked on all 89 channels, both settings.**
Confirmed directly in every channel's `false_counts.leash` and
`n_leash_events` in both new result files — all zero, no exceptions.
Same conclusion as the original 16 holds at full scale: leash's
window/soft/hard-duration settings are test-fixture choices, not
derived from real hardware behaviour, and plainly don't match
whatever sustained drift exists in real ESA-ADB data, if any.

**Context windows (1min/10min/1hour) give identical results on every
new channel — confirmed, and the cause is an existing, already-
documented scope limit, not a bug.** `learn_context.py`'s
training-only command/event correlation was explicitly scoped, by its
own module docstring (written before job2 existed), to only the
original 16 channels' selection: "scoped to the 8 channels already
selected for scoring per mission... going wider here wouldn't change
what GRACIE sees." Checked directly in `linked_trigger_times()`
(`run_esa_adb_test_v2.py`): for any channel outside that original set,
`context_result.get(channel, {})` returns `{}` regardless of window
name, so there is nothing for a wider window to find, on any of the 89
new channels, at any width. Not a wiring bug in job2 — job2 calls the
same function the same way for every channel. Not fixed here —
extending `learn_context.py`'s correlation to 89 more channels is new
work (re-running training-only correlation against them), a separate
decision.

### Per-event catch rate

> Predates GRACIE's clock-health rule too, same as the rest of Job 2
> — see the note at the top of this section.

GRACIE watches the whole ship: an event flagged on at least one of its
channels counts as caught, even if most of its channels individually
missed it. Computed by a new background job (job 6,
`bg_jobs/queue/job6_per_event_catch_rate.py`) that reruns every
monitored channel's scoring with event-ID tracking added — additive
only, `score_channel_variant`'s existing behaviour is unchanged for
every other caller — then unions each event's catch status across
every channel it touched. Self-checked throughout: every channel's
recombined row-level counts were compared against its real per-channel
scorecard above as job 6 ran; the one real bug this caught was in the
check itself (comparing per-event counts against per-row real counts —
fixed, then confirmed against a fresh rerun of a sample afterward), not
in the scoring, which matched the saved per-channel results exactly
everywhere it was checked.

| Mission | Setting | Category | Distinct events | Flagged on ≥1 channel | Any-logged on ≥1 channel |
|---|---|---|---|---|---|
| M1 | STRICT | Anomaly | 34 | 19 (55.9%) | 23 (67.6%) |
| M1 | LOOSE | Anomaly | 34 | 17 (50.0%) | 18 (52.9%) |
| M1 | STRICT | Rare Event | 19 | 13 (68.4%) | 15 (78.9%) |
| M1 | LOOSE | Rare Event | 19 | 12 (63.2%) | 13 (68.4%) |
| M2 | STRICT | Anomaly | 2 | 0 (0%) | 1 (50.0%) |
| M2 | LOOSE | Anomaly | 2 | 0 (0%) | 0 (0%) |
| M2 | STRICT | Rare Event | 195 | 186 (95.4%) | 195 (100%) |
| M2 | LOOSE | Rare Event | 195 | 186 (95.4%) | 194 (99.5%) |

Counts are whole-ship (all 105 monitored channels, the original 16
plus job 2's 89) — see the Mission2-Anomaly correction below.

**The whole-ship view tells a different story than the per-channel
one, in both directions.** Mission1 Anomaly: STRICT catches MORE
distinct events than LOOSE (19 vs 17) — the opposite of the
per-channel table above, where LOOSE's level-flagged count edges out
STRICT's (84 vs 83). Spread the same catches and misses across a
47-channel event and a handful of smaller ones, and which setting
"wins" depends on which lens is used. Mission2 Rare Event is the most
dramatic swing: only 1,588/2,960 (53.6%) of channel-label pairs are
level-flagged under STRICT, but that's 186 of 195 distinct events
(95.4%) — a Rare Event here is almost always caught by SOME channel,
even though any one channel alone looks unreliable.

**The 47-channel event: caught, on 27 of its 47 channels (57.4%,
STRICT).** `id_145` — the single Anomaly event behind nearly half of
Mission1's 247 "Anomaly" label-rows — was flagged FAULT on 27 of the
47 channels it touched, and logged (any sense) on more. Caught by the
whole-ship standard, and not a close call either way: well over half
its own channels caught it too.

**Mission2's "zero catches" needs a small correction once the
original 16 are included.** The 14-channel event (`id_635`) is still
a complete miss — 0/14 channels, flagged or logged, either setting.
But the original 16's own Mission2 Anomaly labels contain a SECOND,
different event that never appears on any of the 39 new channels at
all — so the whole-ship Anomaly count is **2 distinct events, not 1**.
That second event was logged (some sense, WARNING-level) on at least
one channel under STRICT, never under LOOSE, and never reached FAULT
under either setting. The "zero catches" finding holds — still 0/2
flagged, both settings — just for 2 events, not 1.

**The original 16's own 40/106/3/358 label counts are inflated the
same way, and are mostly the SAME events as the new channels', not an
independent sample.** Redone with the identical method: Mission1's 40
Anomaly labels are **19 distinct events** (not 40); 106 Rare Event
labels are **19 distinct events** (not 106). Mission2's 3 Anomaly
labels are **2 distinct events** (not 3 — see above); 358 Rare Event
labels are **176 distinct events** (not 358). Checked for overlap, not
assumed: 19/19 (M1 Anomaly), 19/19 (M1 Rare Event), 1/2 (M2 Anomaly),
and 176/176 (M2 Rare Event) of those ALSO carry a label on at least one
of job 2's 89 channels — the same physical events, visible through a
different channel window, not independent confirmation of a bigger
total. Only Mission2's second Anomaly event is genuinely
original-16-only.

### What wasn't done (per-event catch rate)

- Jump and leash's own per-event rates weren't broken out from "any"
  above — leash is already known to be zero everywhere (see above),
  and jump never reaches FLAGGED (module docstring, point 3), so only
  level/any were worth a table here.
- Per-episode per-event rates weren't computed — same per-reading-only
  scope as the rest of job 2's write-up.

### What wasn't done (job 2)

- Per-episode counts exist in both result files (same schema as the
  v2 rerun's own per-episode breakdown above) but weren't pulled into
  this write-up — every number above is per-reading.
- Per-event catch rate: done — see "Per-event catch rate" above.
- `learn_context.py`'s correlation was not re-run or extended to the
  new 89 channels (see above) — context-checking remains a no-op for
  every channel outside the original 16.
- Jump's cross-check and leash's context-gating — still not built.
- Every number in this section and "Per-event catch rate" predates
  GRACIE's clock-health rule (commit `e6053f7`) — see the note at the
  top of this Job 2 section. Not rerun yet, by design: held until the
  next batch of GRACIE changes (EDEN excused-vs-genuine, standard
  release/latch clearing, the sim scorer fix) is done, then everything
  reruns once, together, from a fresh frozen snapshot of the
  then-current code — not piecemeal.
- Still a first test at this scale, not a validation.
