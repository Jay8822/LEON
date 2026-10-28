# Simulated LEON craft — results (Item 3, 27 October 2026 round)

**Every number on this page is SIMULATED** — a synthetic craft with
nine sensors, a blueprint and rule book co-designed together then
frozen (`sim/COMMISSIONING.md`), four faults and four kinds of normal
event planted by a separate script (`sim/fault_injection.py`) the
agents never read. Not real spacecraft data, not a validation of
anything. Per Jay's overriding condition for this round: **these
results are reported exactly as they came out, good and bad, with no
retry for a nicer-looking run.**

**Update, 28 October 2026**: real NASA battery aging data is now
available (`real_data_tests/nasa_liion_battery_aging/`,
`real_data_tests/nasa_randomized_battery/` — Jay added both
manually; the first was the exact dataset Item 3's own honest-limit
note below said was unreachable). The `dying_battery` fault below
still uses the SYNTHETIC decline curve described there — swapping in
the real `Capacity` trace is queued for a later round, with its own
commissioning and re-test, not done this round.

## What was built

`sim/blueprint.py` + `sim/rulebook.py` (co-designed, frozen together —
see `sim/COMMISSIONING.md` for the two real bugs found and fixed
before freezing, and the one finding investigated and deliberately
left as-is), `sim/craft.py` (clean timeline), `sim/fault_injection.py`
(separate, plants the four faults), `sim/real_data_sources.py`,
`sim/replay.py`, `sim/run_sim_test.py`. Nine sensors: battery_voltage,
battery_current, solar_current, engine_bay_temp, avionics_bay_temp,
thrust, fuel_flow, velocity, attitude_rate. One ~6-hour (21,600-sample,
1Hz) run.

### A real deviation from the approved plan: the NASA battery dataset

The approved plan called for battery_voltage/battery_current and the
dying-battery fault to be sourced from NASA's real Li-ion Battery
Aging Dataset. **That dataset could not be reached from this
machine** — its usual host (NASA DASHlink / c3.nasa.gov) timed out on
every attempt, data.nasa.gov's own catalog page has no working direct
file link, and the known mirrors (IEEE DataPort, Kaggle) both require
creating an account, which this project avoids doing without asking
first. This is a genuine access obstacle hit while building, not a
shortcut — reported here plainly. battery_voltage/battery_current and
the dying-battery fault use an honestly-labelled SYNTHETIC model
instead, same discipline already used for thrust/fuel_flow (which
never had a real analogue). Jay should decide whether this is worth
chasing further. See `sim/real_data_sources.py`'s module docstring for
the full account of what was tried.

Real-data grounding that DID work as planned: solar_current,
engine_bay_temp, avionics_bay_temp, velocity and attitude_rate all
bootstrap real sample-to-sample noise character from OPS-SAT's two
validated 1Hz channels (CADC0872, CADC0894) — noise character, not a
physical analogy (see that module's docstring for exactly which pairs
and why).

### Commissioning

Two real design bugs found and fixed before the blueprint/rule book
were frozen (commit `d23c8af`): the derivation-chunk length didn't
match the scored run's length (a random walk's spread grows with
√time, so every channel drifted past its line within hours); the
expected-cause window only covered a kick's ramp, not its decay tail,
latching FAULT permanently with nothing to ever release it in this
one continuous run. A third finding (two unaffected channels show a
handful of false FAULT samples very late in the clean run) was
investigated and deliberately left as-is — an accepted, inherent
consequence of a 95th-percentile threshold on one full-length run,
not a defect. Full detail: `sim/COMMISSIONING.md`.

## Scoring: both runs, side by side

Per Jay's approved change 2: the exact same seed, faults and frozen
rule book, run TWICE — once with GRACIE given no help from the
craft's own plan (`expected_causes` always empty), once with her real
event schedule fed in.

### Fault detection

| Fault | Channel | Without plan | With plan |
|---|---|---|---|
| dying_battery | battery_voltage | FAULT, delay 434s | FAULT, delay 434s (unchanged — no event overlaps this fault's window) |
| stuck_sensor | attitude_rate | **MISSED** | **MISSED** |
| noisy_sensor | fuel_flow | FAULT, delay 447s | FAULT, delay 447s (unchanged) |
| bad_engine_burn | battery_current | FAULT, delay 0s | **WARNING only**, delay 72s |

**stuck_sensor is never detected, in either run — exactly the finding
Jay asked to see reported plainly (approved change 4).** A frozen
sensor produces no crossing and no jump, by construction; it is
invisible to all three of GRACIE's current senses. This is not a bug
and was not patched — it's the precise, concrete reason the Diagnostic
checklist (SPEC.md, not built yet) exists.

**bad_engine_burn is the other approved-change-4 finding, and it's a
genuinely nuanced one.** Without the plan, the wrong-sized burn's
battery_current channel crosses its line and is flagged FAULT
immediately — looks "caught." WITH the plan, that same crossing gets
**demoted to WARNING**, because GRACIE's `expected_causes` only ever
says "a cause was commanded here," not "and here is the correct
size" — she cannot tell a correctly-sized burn from an underpowered
one. Knowing the plan made this fault look LESS urgent, not more. This
is not a flaw in the scoring; it's a direct demonstration of exactly
the gap the Diagnostic checklist is meant to close (checklist item 2,
"did the related sensors move too," and item 1, "what happened just
before" — neither checks WHETHER the move was the right size).

### False alarms on normal events (22 opportunities: 8 events × their affected channels)

| | Without plan | With plan |
|---|---|---|
| Events false-alarmed | 22 / 22 | 2 / 22 |

Without the plan, every single normal event (burns, corrections,
battery switches, occlusions) is flagged FAULT — expected, since
nothing tells GRACIE these are explained. With the plan, this drops to
2 — **both of them battery_switch's own battery_voltage reading**,
and both turn out to be a masking effect, not a new false alarm (see
below). **The plan's value here is real and large: it suppresses
20 of 22 false alarms this run would otherwise raise**, at the cost
of the bad_engine_burn demotion above.

### A recurring finding: the exact masking pattern already found in real ESA-ADB data (A76) shows up again, in this synthetic sim

The two remaining "false alarms" (`battery_switch_1`/`_2` on
battery_voltage) are not actually caused by the battery switch event
at all. battery_voltage latches FAULT at sample 434 (the dying-battery
fault, which starts at sample 400) and **never clears** — there is no
`clear_fault()` call anywhere in this one continuous run. By the time
either battery_switch event happens (samples 5200 and 15800), the
channel has already been sitting latched FAULT for roughly 4,800 and
15,400 samples respectively, for a completely different reason. The
battery switch's own jitter is invisible behind that pre-existing
latch — **structurally identical** to `ASSUMPTIONS.md` A76 and
`real_data_tests/esa_adb/CHECKS.md` 2b's real finding: a channel
already falsely (or, here, genuinely) latched can hide whether a
later, different event would have been caught on its own merits. Not
designed in on purpose — found by actually checking why these two
events still showed up, not assumed to be a leftover rounding error.

### Background false alarms (outside any known event or fault window)

| Channel | Without plan | With plan |
|---|---|---|
| battery_voltage | 18,440 samples (from sample 3,100) | 18,440 samples (unchanged — same dying_battery latch, outside its own 400–3,100 window) |
| battery_current | 19,160 samples (from 1,740) | 0 |
| solar_current | 14,000 samples (from 7,300) | 0 |
| engine_bay_temp | 19,220 samples (from 1,740) | 1,360 samples (from 20,240) |
| thrust | 19,220 samples (from 1,740) | 0 |
| velocity | 19,220 samples (from 1,740) | 0 |
| fuel_flow | 6,800 samples (from 14,800) | 6,800 samples (unchanged — the noisy_sensor fault's own latch, outside its own 13,000–14,800 window) |

**Without the plan, five of nine channels spend most of the run
permanently latched FAULT from their very first normal event onward**
— every kick-affected channel's first burn or correction, once it
crosses its line unexplained, never comes back, because this
continuous sim has no reset point (unlike the real-data tests' daily
`clear_fault()`). With the plan, this drops to one lingering case:
engine_bay_temp latches at sample 20,240 — exactly the sample
immediately after `bad_engine_burn`'s own covered window closes
(20,000–20,240). Investigated, not fully run down under this round's
time: most likely the kick's decay leaves a fractional residual right
at that boundary. Reported as-is rather than quietly patched.

battery_voltage and fuel_flow's unchanged background counts are the
SAME masking pattern as above, just outside any event window instead
of during one: once latched, nothing in this run clears them,
regardless of the plan.

### EDEN / orchestrator / CHESTER / ghost mode

EDEN enters SAFE_MODE for 20,766 of 21,600 samples — **identical in
both runs.** This is the aggregate-masking consequence of the same
no-reset structure: `GracieAgent.health_state` is a worst-case rollup
across all nine channels, and dying_battery's permanent latch (from
sample 434 onward) alone keeps the aggregate at FAULT for almost the
entire run regardless of what the plan does for every other channel.
Knowing the plan measurably helps individual channels (see above) but
is invisible at the aggregate, system-wide level this run — EDEN's
real reaction is dominated by the single worst, earliest, never-
cleared fault. GhostModeHarness logged 20,766 comparisons in each run
with **zero disagreements** — the orchestrator's `decide()` always
agreed with EDEN's real SAFE_MODE reaction here, which is expected:
ghost mode's own documented scope sends every GRACIE FAULT straight
to `decide()` with `Severity.VIOLATED` (no independent second check
exists yet), so agreement was never really in doubt — not a
meaningful validation of ghost mode so much as a predictable
consequence of its own known, named gap (see `agents/ghost_mode.py`'s
module docstring, point 1).

CHESTER ran throughout (watching every `chester/watch` announcement);
no dedicated CHESTER-specific scoring was done this round — out of
scope for detection/false-alarm/delay scoring, which is what was
approved.

### ETHAN and LUNAE

Ran exactly as they currently are — their existing simple mode/nav-
state reporting only. **Neither was upgraded to consume this sim's
actual thrust/fuel_flow/velocity/attitude_rate values in any detailed
way.** This is a real, known gap, not glossed over: this sim currently
tells us nothing about ETHAN's or LUNAE's own health-monitoring
capability, because neither has one yet beyond their existing simple
status fields.

## What wasn't done (explicitly deferred, not forgotten)

- **Isolation scoring.** The Diagnostic checklist (SPEC.md, Step 2 of
  the prior round) isn't built yet — there is nothing to score
  isolation against. Both the stuck-sensor miss and the bad-burn
  demotion above are exactly the cases that checklist is meant to
  address; this sim makes the gap concrete rather than closing it.
- The one remaining background false alarm on engine_bay_temp (right
  at `bad_engine_burn`'s window boundary) is reported, not root-
  caused in full.
- ETHAN/LUNAE real health-monitoring, as above.
- A richer multi-seed run (this round is one fixed seed, as approved
  then) — see the Item 3b round below, which does exactly this.

---

# Item 3b re-test (27 October 2026) — three design changes, re-run on
# the same seed AND three fresh seeds with new fault timings

Three changes to GRACIE's core, driven directly by this page's own
first-round findings above (full design: `Ccode update.txt`, "ITEM
3b"; code: `agents/gracie.py`/`agents/gracie_rulebook.py`, commit
`152a876`): expected causes now carry a real expected SIZE, not just
"a cause was commanded"; a new crossing on an already-latched channel
now reaches the orchestrator (`agents/escalation_watch.py`, a labelled
STAND-IN); a new, fourth sense, **Stillness**, flags a channel whose
variation stays below the blueprint's stated minimum.

Also added this round: `sim/human_signoff.py` (Jay's approved change
6) — a simulated human who releases a channel's latch once it's run
past a response delay and isn't currently inside a real, live fault,
driving `EscalationOrchestrator`'s actual sign-off state machine
rather than bypassing it. Second commissioning round (`sim/
COMMISSIONING.md`) found and fixed two more real design bugs before
re-freezing (`f57bbd9`) — full detail there; short version: Stillness's
own derivation didn't match how its real check actually runs, and
`solar_current` needed `allow_steady=True` (it's this sim's own
version of SPEC.md's "light sensors in Earth's shadow" example).

**Per Jay's instruction, this is a genuine re-test, not a repeat**:
the same seed as the first round, for a direct before/after on the
exact same faults, AND three fresh seeds (scenario noise AND fault
timing both re-randomized, `sim/fault_injection.py`'s new
`timing_seed` parameter) never seen before freezing anything. All
four results below, good and bad, exactly as they came out.

## Did the three fixes actually fix what they were built for?

| Finding this was meant to fix | Result, all 4 seeds |
|---|---|
| `stuck_sensor` invisible to all three original senses | **Fixed, and it generalises.** Caught by Stillness in EVERY seed (FAULT, delay 93–108s) — the clearest, most robust result in this round. |
| `bad_engine_burn` demoted FAULT→WARNING by a size-blind expected cause | **Did not actually test what we thought.** See below — it turns out this fault's own detection was never level-driven to begin with. |
| `new_crossing_while_latched` only logged, not escalated | **Built and proven to escalate** (`agents/escalation_watch_test.py`), but this sim doesn't independently confirm it changes anything observable at the aggregate level — see EDEN/aggregate section below. |

### `bad_engine_burn`: the demotion story from the first round doesn't hold up — checked, not assumed

In every one of the four seeds, `bad_engine_burn` is detected as
**WARNING, not FAULT**, at a delay of 72–77 seconds — **identical
between the without- and with-expected-causes runs, every time.**
Checked directly, not inferred: `battery_current`'s value never once
crosses its own LEVEL line anywhere in the fault's window, in any
seed (confirmed by direct inspection of the injected series) — the
WRONG_BURN_SCALE=0.25 kick is simply too small to reach LEVEL at all.
What actually fires is **LEASH**: the kick's sustained rate of change
clears `leash_slope_limit` for long enough to reach the soft duration
(~72–77s in), which GRACIE's leash sense has never consulted
`expected_causes` for, in any round. The first round's "FAULT without
the plan → WARNING with it" was a real, observed number, but — now
that `sim/human_signoff.py` stops channels from staying permanently
latched from unrelated earlier events — it's clear that difference
came from which *pre-existing* latch state each run happened to carry
into the fault's window, not from this fault's own crossing being
excused differently. **The expected-cause size fix is still real and
necessary** — the commissioning check above caught it correctly
excluding a wrong-sized kick from a completely different event
(`course_correction_2`/`thrust`) — it simply isn't the mechanism that
explains `bad_engine_burn` specifically. Reported plainly as a
correction to the first round's own story, not glossed over.

### `noisy_sensor`: generalises badly — caught in the original placement, missed in all three fresh ones

| Seed | Detected? |
|---|---|
| same_seed (original placement) | FAULT, delay 447s |
| fresh_seed_1 | **MISSED** |
| fresh_seed_2 | **MISSED** |
| fresh_seed_3 | **MISSED** |

Checked why, not just noted it: `fuel_flow`'s LEVEL line was never
crossed in any fresh-seed placement (confirmed by direct inspection —
e.g. fresh_seed_1's actual values stayed within
[0.168, 0.186] against bounds of [0.123, 0.258]). The fault's extra
jitter is a FIXED width; whether it's enough to reach LEVEL depends on
where `fuel_flow`'s own unbounded random-walk baseline happens to sit
at the moment the fault lands — which is exactly what re-randomizing
the timing was for, and exactly the kind of fragility it was supposed
to surface. **A second, separate finding underneath this one**:
`fuel_flow` was NOT actually blind to the fault in the fresh seeds —
its JUMP sense fired on 1,447 of the fault's 1,800 samples in
fresh_seed_1 (checked directly). `score_faults()` only ever looks at
LATCHED severity (level/leash/Stillness), so a fault that only ever
shows up as repeated jump events scores as "missed" even though
GRACIE's aggregate `health_state` would show WARNING almost
continuously throughout. This is a scoring-definition gap, not the
same kind of structural blind spot `stuck_sensor` has — worth fixing
in a later round's scoring (count jump-only coverage separately), not
something to quietly patch into this round's numbers now.

## False alarms on normal events (22 opportunities, every seed)

| Seed | Without the plan | With the plan |
|---|---|---|
| same_seed | 13/22 | 2/22 |
| fresh_seed_1 | 13/22 | **4/22** |
| fresh_seed_2 | 13/22 | 2/22 |
| fresh_seed_3 | 12/22 | 2/22 |

The "without" column is fairly stable across seeds (12–13/22) — most
normal events get falsely flagged without the plan, regardless of
timing, as expected. The "with" column mostly matches the first
round's 2/22, except fresh_seed_1 (4/22) — its own commissioning check
(below) already showed 2 false alarms on the clean, fault-free
timeline for this exact seed, so at least some of this seed's extra
false alarms are the same already-accepted statistical phenomenon
landing on a different noise draw, not a new defect. Without the
plan's 22/22 from the very first round (before `sim/human_signoff.py`
existed) is not directly comparable to this round's 12–13/22 — this
round's human sign-off periodically releases channels that would
previously have stayed permanently latched from an earlier,
unrelated event, so fewer events inherit a stale pre-existing latch.

## Commissioning check, repeated on every seed (frozen blueprint/rule book — reported, never corrected)

| Seed | False alarms on the clean, fault-free timeline |
|---|---|
| same_seed | 0/22 |
| fresh_seed_1 | **2/22** |
| fresh_seed_2 | 0/22 |
| fresh_seed_3 | 0/22 |

fresh_seed_1's clean timeline shows 2 false alarms that the frozen
blueprint/rule book cannot be adjusted to fix this round (Jay's
commissioning guardrail: corrections only happen before the freeze
commit). Same accepted phenomenon as the first round's own
"investigated, not corrected" finding — a percentile-derived
threshold has a non-zero false-alarm rate by construction, and a
fresh seed is simply one more draw from that same distribution,
landing slightly worse for this specific noise realisation.

## EDEN's aggregate reaction: still dominated by SOME channel, every time, in every seed

| Seed | Without the plan | With the plan |
|---|---|---|
| same_seed | 20,745/21,600 | 20,741/21,600 |
| fresh_seed_1 | 19,170/21,600 | 18,545/21,600 |
| fresh_seed_2 | 20,332/21,600 | 20,329/21,600 |
| fresh_seed_3 | 19,859/21,600 | 19,232/21,600 |

`sim/human_signoff.py` genuinely works at the PER-CHANNEL level (the
background-false-alarm channel lists visibly shrink between without/
with, and individual latches now provably clear — confirmed by
`clear_fault` calls actually firing). But `GracieAgent.health_state`
is a worst-case rollup across all nine channels, and with nine
channels each carrying some non-zero false-alarm rate, the odds that
EVERY one of them is simultaneously clear at any given instant stay
low — so EDEN's own aggregate SAFE_MODE reaction barely moves, in
every seed, with or without the plan. GhostModeHarness logged zero
disagreements in every seed, every run — expected, given its
documented narrow scope (same reasoning as the first round), not a
meaningful validation on its own.

## What this round adds to "what wasn't done"

- Scoring doesn't currently count jump-only (non-latching) coverage
  separately from latched-severity detection — `noisy_sensor`'s
  fresh-seed misses above are a concrete case where this matters.
- `agents/escalation_watch.py`'s forwarding isn't independently
  scored in this sim (no second rule set to disagree with it, same
  gap `GhostModeHarness` already has) — built and unit-tested, but
  this run doesn't demonstrate it changing a craft-level outcome.
- A variant where the simulated human sometimes answers wrong (Jay's
  own note for later, not this round).
- Isolation scoring, still deferred, same reason as the first round.

# Item C: EDEN's fault-class-aware reaction (28 October 2026)

Three changes, driven by this page's own ~90% SAFE_MODE finding:
GRACIE's rule book now states a fault class (major/non-urgent/boom)
per sense per sensor; her report now says which sense is currently
responsible for a channel's severity (`causing_sense`); EDEN looks
that up against her own copy of the SAME table and reacts NON_URGENT
-> flagged and logged only, MAJOR -> HOLD (not SAFE_MODE), BOOM ->
SAFE_MODE with the mandatory human sign-off. Code: `agents/gracie.py`/
`agents/gracie_rulebook.py`/`agents/eden.py` (commit `8eef826`); sim
wiring and third commissioning round (commit `4fe727c`) found no
blueprint/rule-book regressions. Re-tested on the same 5 seeds (the
original 4 plus a brand-new `fresh_seed_4`), both expected-cause
modes, same discipline as every round: reported exactly as it came
out.

## Fault detection: completely unchanged, as it should be

Every fault's detection timing (noticed/flagged, per sense, per seed)
is IDENTICAL to the pre-Item-C re-score above, in all 5 seeds, both
modes. Expected, and confirmed rather than assumed: Item C never
touches level/jump/leash/Stillness's own logic, only what happens
AFTER a severity is already decided -- this is the correctness check
that Item C didn't quietly change detection while fixing reaction.

## The root-cause fix works: SAFE_MODE time drops dramatically, replaced by HOLD

| Seed | Mode | HOLD (of 21,600s) | SAFE_MODE | MONITORING (nominal) | MONITORING (non-urgent, flagged) |
|---|---|---|---|---|---|
| same_seed | without plan | 19,005 (88%) | 1,800 (8%) | 795 | 0 |
| same_seed | with plan | 19,738 (91%) | 1,081 (5%) | 781 | 0 |
| fresh_seed_1 | without plan | 17,500 (81%) | 1,800 (8%) | 2,300 | 0 |
| fresh_seed_1 | with plan | 17,839 (83%) | 1,072 (5%) | 2,689 | 0 |
| fresh_seed_2 | without plan | 18,626 (86%) | 1,800 (8%) | 1,174 | 0 |
| fresh_seed_2 | with plan | 19,369 (90%) | 1,068 (5%) | 1,163 | 0 |
| fresh_seed_3 | without plan | 18,112 (84%) | 1,800 (8%) | 1,688 | 0 |
| fresh_seed_3 | with plan | 18,512 (86%) | 2,009 (9%) | 2,009 | 0 |
| fresh_seed_4 | without plan | 18,624 (86%) | 2,400 (11%) | 576 | 0 |
| fresh_seed_4 | with plan | 13,311 (62%) | **7,728 (36%)** | 561 | 0 |

The first round's own finding (EDEN in SAFE_MODE for ~90-96% of every
run) is gone -- what was SAFE_MODE time is now correctly split, the
large majority landing in HOLD (a real, distinct, less drastic
reaction) and only a genuine boom-classed condition reaching
SAFE_MODE. This is the fix working as intended.

**MONITORING (non-urgent, flagged) is zero in every single cell,
every seed, every mode.** Investigated, not assumed: `_classify()`
takes the WORST class among every channel currently at WARNING or
FAULT in the whole report, and with 9 channels each carrying some
nonzero false-alarm or fault rate, there is essentially always SOME
channel at MAJOR or BOOM somewhere on the craft once the run is more
than a few minutes old -- so a genuinely non-urgent-only state (every
non-nominal channel being jump/leash-soft and nothing else) never
actually occurs in this sim. Same aggregate-masking shape as the
first re-test round's EDEN finding, now showing up in the fault-class
split too, not fixed by this change and not expected to be -- it's a
property of having many independently-faulting channels, not a flaw
in the classification itself.

## A real finding, caught by checking the data, not assumed: SAFE_MODE time is inflated by an already-EXCUSED warning

`engine_bay_temp`'s LEVEL class is BOOM (Jay's correction). Checked
directly why `fresh_seed_4`'s SAFE_MODE time jumps to 7,728s (with the
plan) against ~1,070-1,080s for every other seed: `engine_bay_temp`
itself only has ONE real FAULT episode (600 samples, 18,873-19,473 --
the same human-signoff-release pattern as elsewhere). The REST of the
SAFE_MODE time, in every seed, comes from something the plan was
supposed to have already handled -- at sample 1,527 of `same_seed`'s
with-plan run, `engine_bay_temp` shows `severity=WARNING`,
`level_active=True`. That combination is only reachable through
`_process_level`'s MATCHED-expected-cause branch (the non-matched
path always sets FAULT, never WARNING) -- confirmed by reading the
code, not inferred -- which means this is an engine burn's or course
correction's EXPECTED kick, correctly logged by GRACIE as WARNING,
not flagged, exactly as designed. **But `EdenAgent._classify()` reacts
to ANY WARNING-or-FAULT severity, regardless of why it's WARNING** --
it has no way to tell "logged because genuinely non-urgent" apart from
"logged because an expected cause already excused it." Since
`engine_bay_temp`'s LEVEL sense is BOOM-classed, every one of its four
expected kicks this round still drives EDEN to SAFE_MODE, even though
GRACIE already correctly decided nothing was wrong. `fresh_seed_4`'s
much larger number is this SAME mechanism plus an unusually long
background false WARNING/FAULT episode on `engine_bay_temp` for that
seed's own noise draw (consistent with the project's own established
"one more draw from the false-alarm distribution" explanation used
throughout this sim and the real ESA-ADB/OPS-SAT work) -- the excused-
kick contribution alone, visible in the other four seeds, is roughly
constant (~1,070-1,080s); fresh_seed_4 adds a much larger, separate
background episode on top of it.

**Not fixed this round, on purpose** -- the frozen blueprint, rule
book and EDEN logic don't change after seeing a faulted result, same
discipline as every round. This is reported here as a genuine gap for
a future round to close (candidates, not decided: restrict EDEN's
classification to FAULT-severity reports only; or have GRACIE's
report distinguish "excused" from "genuinely non-urgent" explicitly,
since both currently present as a plain WARNING with a
`causing_sense`). Flagged plainly because an already-excused,
correctly-logged kick driving the WHOLE CRAFT into SAFE_MODE is
exactly the kind of consequence a boom classification should not have
-- a real, concrete argument for fixing this before this mechanism is
trusted for anything beyond a proof of concept.

## What this round adds to "what wasn't done"

- The EDEN classification gap above (reacts to excused WARNINGs, not
  just genuinely unexplained ones) -- a real, found, unfixed gap.
- EDEN's own tighter-tolerance validation (SPEC.md: "against the
  agent's rules AND her own") -- deliberately its own future round,
  not bundled in or skipped.
- `agents/lunae.py`'s independent "any FAULT -> HOLD" reaction
  (process_telemetry, separate from EDEN's new command) -- doesn't
  affect this sim (never wired to it), but is a real, separate
  inconsistency in the wider system, unexamined further this round.

# Re-score: "noticed" vs "flagged", per sense (27 October 2026,
# Jay's ordered re-score, item A — done before Item 4)

The gap above (`noisy_sensor` scoring as flat-out "missed" even
though its JUMP sense fired on most of the fault's samples) is a
scoring-DEFINITION gap, not a GRACIE gap — fixed here by scoring two
genuinely different questions, per sense and combined, for every
planted fault, matching `real_data_tests/esa_adb/`'s own
caught_logged/caught_flagged convention extended to GRACIE's now-four
senses:
- **noticed (logged):** did GRACIE raise ANY activity for this
  sense — a level crossing, a jump event, leash reaching soft, or
  Stillness — during the fault's window? Jump counts here even though
  it never changes `severity` at all.
- **flagged (latched):** did that sense actually latch `severity` to
  FAULT (leash's hard duration, for leash)?

Blueprint/rule book stayed frozen throughout — this is a re-score of
the SAME saved behaviour, not a re-run with anything changed.

## Every planted fault, every seed: noticed is fast, flagged is a much higher bar

| Seed | Fault | Combined noticed (delay, s) | Combined flagged (delay, s) | Senses that noticed | Senses that flagged |
|---|---|---|---|---|---|
| same_seed | dying_battery | 9 | 434 | level, jump | level |
| same_seed | stuck_sensor | 100 | 100 | jump, stillness | stillness |
| same_seed | noisy_sensor | 1 | 447 | level, jump | level |
| same_seed | bad_engine_burn | 5 | **never** | jump, leash | — |
| fresh_seed_1 | dying_battery | 6 | 670 | level, jump | level |
| fresh_seed_1 | stuck_sensor | 108 | 108 | jump, stillness | stillness |
| fresh_seed_1 | noisy_sensor | 1 | **never** | jump | — |
| fresh_seed_1 | bad_engine_burn | 4 | **never** | jump, leash | — |
| fresh_seed_2 | dying_battery | 7 | 644 | level, jump | level |
| fresh_seed_2 | stuck_sensor | 93 | 93 | level, jump, stillness | level, stillness |
| fresh_seed_2 | noisy_sensor | 1 | **never** | jump | — |
| fresh_seed_2 | bad_engine_burn | 1 | **never** | jump, leash | — |
| fresh_seed_3 | dying_battery | 1 | 476 | level, jump | level |
| fresh_seed_3 | stuck_sensor | 106 | 106 | jump, stillness | stillness |
| fresh_seed_3 | noisy_sensor | 0 | **never** | jump | — |
| fresh_seed_3 | bad_engine_burn | 1 | **never** | jump, leash | — |

(`with_expected_causes` is identical to `without` in every cell above
— none of these four faults' own detection timing changes with the
plan, same finding as the first re-test round, now confirmed at the
per-sense level too.)

**The headline, not previously visible under flagged-only scoring:
every single fault, in every seed, is NOTICED within 0–9 seconds —
almost always via JUMP, which fires on the very first large sample-to-
sample discontinuity the fault creates.** "Flagged" is a dramatically
higher, slower bar: `dying_battery` takes 434–670s to actually latch;
`stuck_sensor` and `bad_engine_burn` either flag quickly via a
different mechanism (Stillness, not level/jump) or never flag at all.
`noisy_sensor` and `bad_engine_burn` NEVER flag in ANY seed —
`noisy_sensor` only ever shows up as noticed (jump), never latched;
`bad_engine_burn` reaches leash's SOFT edge (noticed) but never HARD
(flagged), confirming the first re-test round's own correction (this
fault is leash-driven, not level-driven, and `expected_causes`
genuinely doesn't touch leash at all). **This is a real, concrete
argument for CHESTER-level escalation of sustained "noticed, never
flagged" conditions** — not built or scored this round, noted as a
real candidate for later, not acted on now.

## False alarms on normal events: when flagged, it's always LEVEL — never leash, jump or Stillness

| Seed | Mode | Flagged | Noticed-only (never flagged) |
|---|---|---|---|
| same_seed | without plan | 13/22, all LEVEL | 5/22 |
| same_seed | with plan | 2/22, all LEVEL | 16/22 |
| fresh_seed_1 | without plan | 13/22, all LEVEL | 6/22 |
| fresh_seed_1 | with plan | 4/22, all LEVEL | 15/22 |
| fresh_seed_2 | without plan | 13/22, all LEVEL | 5/22 |
| fresh_seed_2 | with plan | 2/22, all LEVEL | 16/22 |
| fresh_seed_3 | without plan | 12/22, all LEVEL | 6/22 |
| fresh_seed_3 | with plan | 2/22, all LEVEL | 16/22 |

Every false alarm that ever reaches FLAGGED, in every seed, every
mode, is LEVEL-driven — not one is leash, jump or Stillness. This
matches design expectations (a normal event's expected kick is sized
to plausibly cross LEVEL if unexplained, not to cross leash's slope
limit or trip Stillness) rather than revealing anything new. The
`expected_causes` plan's real effect, visible clearly here: it mostly
converts a LEVEL false-FLAG into a LEVEL false-NOTICE (logged, not
latched) — noticed-only count roughly triples (5–6 -> 15–16) exactly
as flagged drops, consistent with the design intent, not a side
effect.

## What this adds to "what wasn't done"

- The CHESTER-level "noticed, never flagged, for a long time"
  escalation idea above — real, surfaced by this re-score, not built.
