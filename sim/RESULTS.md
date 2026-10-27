# Simulated LEON craft — results (Item 3, 27 October 2026 round)

**Every number on this page is SIMULATED** — a synthetic craft with
nine sensors, a blueprint and rule book co-designed together then
frozen (`sim/COMMISSIONING.md`), four faults and four kinds of normal
event planted by a separate script (`sim/fault_injection.py`) the
agents never read. Not real spacecraft data, not a validation of
anything. Per Jay's overriding condition for this round: **these
results are reported exactly as they came out, good and bad, with no
retry for a nicer-looking run.**

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
- A richer multi-seed run (this round is one fixed seed, as approved).
