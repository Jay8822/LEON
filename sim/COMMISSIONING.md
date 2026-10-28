# Simulated LEON craft -- commissioning log

Per Jay's approved change 3 on Item 3 (27 October 2026): before any
fault exists, the clean timeline (sim/craft.py's events, no faults)
was run through GRACIE with the blueprint's own derived rule book
(sim/blueprint.py, sim/rulebook.py), with the craft's real event
schedule fed to her as `expected_causes`. Every correction made along
the way is logged here with its reason, as real spacecraft
commissioning would. Two real corrections were needed; a third
apparent issue was investigated and is an accepted, understood
consequence of the chosen threshold method, not a defect -- also
logged here rather than silently left unexplained.

## Correction 1 -- derivation chunk length didn't match the scored run's length

**Finding:** every channel, including ones no event ever touches
(avionics_bay_temp, velocity, attitude_rate), drifted past its own
level/leash line within the first few hundred to few thousand samples
and stayed latched FAULT for virtually the entire 6-hour run.

**Reason:** `sim/blueprint.py`'s derivation used
`DERIVATION_CHUNK_SECONDS = 300`, copied from
`simulated_tests/leash_drift/generate_leash_drift.py`'s own constant
without checking whether it matched THIS sim's own, much longer
scored-run length (21,600 seconds). A random walk's spread grows with
the square root of elapsed time, so bounds derived from 300-second
chunks were calibrated for roughly 1/8.5th of the actual run's natural
spread -- the walk was given far more room to wander than the bounds
accounted for.

**Fix:** `DERIVATION_CHUNK_SECONDS` changed to 21,600 -- the same
length as the scored run -- so the percentile-derived bounds are
calibrated against walks of the same duration they're later tested
against. This is the same practice `real_data_tests/esa_adb/` and
`real_data_tests/opssat_ad/` already use (training chunks comparable
in length to what they're later scored against); this file should
have followed it from the start instead of copying a shorter-duration
precedent's constant unchecked.

**Verified:** re-ran the clean timeline after the fix -- the three
channels with no event at all (solar_current, avionics_bay_temp,
attitude_rate) dropped to zero false FAULT samples.

## Correction 2 -- the expected-cause window only covered a kick's ramp, not its decay

**Finding:** engine_bay_temp, battery_current, thrust and velocity
(every "kick"-affected channel) still latched FAULT, starting exactly
at the sample where each event's `expected_causes` window closed.

**Reason:** a "kick" ramps up over the event's stated duration, then
decays back down over an equal following period -- but
`sim/craft.py`'s event records only recorded `end_s = start_s +
duration_s` (the ramp's end), not the decay tail's end. GRACIE was
told the cause stopped being "expected" while the channel was still
physically elevated and still crossing its line, so she saw an
unexplained crossing and latched FAULT -- permanently, since this
sim's one continuous 6-hour run never calls `clear_fault()` the way
the real-data tests' daily resets do.

**Fix:** each event's recorded `end_s` now covers the full kick (ramp
AND decay, `start_s + 2*duration_s`) for "kick"-shaped effects.
"jitter" and "zero" effects have no decay tail, so their `end_s` is
unchanged (`start_s + duration_s`).

**A related design change, same root cause:** velocity's reaction to
a burn was originally a PERMANENT step (a real burn's delta-v
genuinely doesn't decay back) rather than a kick. A permanent step has
no "decay tail" to extend the expected-cause window over -- the
channel stays crossing forever, which GRACIE's current design can
only ever treat as an unexplained, permanently-latched FAULT, because
`expected_causes` only suppresses the MOMENT of crossing; redefining
what "nominal" means afterward is SPEC.md's Ageing mechanism's job (a
slow, human-signed-off baseline update), not exercised this round.
This isn't a blueprint/rule-book numbers problem to correct -- it's a
scope mismatch between what the craft was designed to do (a lasting
velocity change) and what GRACIE's current, unchanged design can
represent. Changed velocity's burn/correction reaction to a temporary
KICK, same shape as the other reactive sensors, for this round --
narrowing the simulated craft to what GRACIE's current capabilities
can actually be tested against, not claiming a real burn's delta-v is
temporary. `sim/blueprint.py`'s `EVENT_EFFECTS` comment carries the
same note.

**Verified:** re-ran the clean timeline after both fixes -- every
event-affected channel (battery_current, engine_bay_temp, thrust,
velocity, solar_current) dropped to zero false FAULT samples.

## Investigated, not corrected -- two channels still show a handful of false FAULT samples very late in the run

**Finding:** battery_voltage (1,070 false FAULT samples, starting at
sample 20,530 of 21,600) and fuel_flow (8,086 false FAULT samples,
starting at sample 13,514) -- neither touched by any normal event --
still cross their own derived lines once, near the end of this
particular run.

**Investigated, not treated as a bug:** both channels' thresholds are
STRICT (95th/5th percentile) bounds derived from 20 independent
21,600-sample derivation walks of the SAME length as the scored run
(Correction 1's fix). By construction, a 95th-percentile bound is
expected to be exceeded by a genuinely nominal walk of the same length
roughly 1 time in 20 -- this scored run's own noise realisation is
simply one more draw from that same distribution, and landed on the
unlucky side for these two channels. This is the same phenomenon
`RESULTS.md`/`CHECKS.md` already document candidly for the real
ESA-ADB and OPS-SAT datasets throughout this project: a percentile-
derived threshold carries an inherent, non-zero false-alarm rate by
design, on channels doing nothing wrong.

**Why this was NOT "corrected":** re-seeding the scenario, or
loosening these two channels' bounds, until this specific run shows
zero false alarms would be tuning the blueprint/rule book against this
run's own result -- exactly what Jay's approved change 3 forbids
("if you're tempted to adjust something after seeing a... result,
stop and report that temptation plainly instead of acting on it") and
what his overriding condition on this whole round rules out directly
("the results must not be concocted to look good"). Reported here
plainly instead, and carried into `sim/RESULTS.md` as genuine,
unprompted false alarms on two otherwise-untouched channels.

## Checkpoint

Corrections 1 and 2 applied; the third finding accepted as-is. No
further changes to `sim/blueprint.py` or `sim/rulebook.py` after this
file's checkpoint commit, whatever `sim/fault_injection.py`'s scored
runs show.

---

# Second commissioning round -- Item 3b (27 October 2026)

Jay's three design changes (expected causes carry a size; a new
crossing while latched reaches the orchestrator; Stillness, a fourth
sense) needed new blueprint/rule-book fields and a new mechanism in
`sim/run_sim_test.py` (real per-sample expected RANGES, not just
channel presence). Re-ran the clean, fault-free timeline again before
touching `sim/fault_injection.py` at all, same discipline as the
first round. Two real corrections needed; both investigated, not
guessed at.

## Correction 3 -- Stillness's own derivation didn't match how the real check actually runs

**Finding:** Stillness fired on almost every channel, including ones
no event ever touches (`avionics_bay_temp`, `attitude_rate`) -- the
exact same symptom shape as Correction 1, a different mechanism.

**Reason:** `min_normal_noise` was derived as a low percentile taken
directly over individual windowed-range samples (one value per
120-second block, 180 per 21,600s derivation chunk). But
`agents/gracie.py`'s real Stillness check re-evaluates a SLIDING
120-second window on EVERY sample, continuously, for the whole run --
21,600 highly-overlapping chances for a dip, not 180 independent
ones. A threshold calibrated against "what's typical for one
isolated window" is nowhere near strict enough once a one-way-ratchet
latch gets that many chances to fire somewhere across a whole run; by
the time any one of those thousands of overlapping checks dips below
the threshold, it won't release itself again until `clear_fault()`.

**Fix:** `sim/blueprint.py`'s `derive_stillness_limit()` now uses the
SAME chunk-extreme-then-percentile-across-chunks discipline every
other limit here already uses (`derive_thresholds`/
`derive_jump_limits`/`derive_leash_limits`): each derivation
fragment's own STILLEST moment (its minimum sliding-window range
anywhere within it, matching the real check's own evaluation
density), then the low percentile taken across fragments' minimums,
not across every individual window.

**Verified:** re-ran the clean timeline after the fix --
`avionics_bay_temp` and `attitude_rate` dropped to zero false FAULT
samples, matching the Stillness-disabled control exactly.

## Correction 4 -- solar_current needed `allow_steady` -- SPEC.md's own named example

**Finding:** even after Correction 3, `solar_current` still showed
Stillness FAULTs for the FULL duration of both `solar_occlusion`
events (300/300 samples each).

**Investigated, confirmed not a bug:** `solar_occlusion` pins
`solar_current` at EXACTLY 0.0 for its whole duration -- zero
variation, by design. This is precisely SPEC.md's own Blueprint
bullet, verbatim: "sensors that legitimately read zero in some
conditions (for example, light sensors in Earth's shadow)."
Stillness was working exactly as designed, correctly flagging
genuinely zero variation -- the blueprint itself was wrong to leave
`solar_current` at the default `allow_steady=False` given its own
`solar_occlusion` event already existed to produce exactly this
condition.

**Fix:** `solar_current`'s `allow_steady` is now `True` -- the one
sensor in this sim with a blueprint-known legitimate steady
condition. Every other sensor stays `allow_steady=False`; none of
them have one.

**Verified:** re-ran the clean timeline -- 0/22 false alarms on
normal events (down from 11/22 before either fix), background false
alarms down to the same two statistically-expected channels
(`battery_voltage`, `fuel_flow`) the first commissioning round's
Correction-1-fix state already showed and accepted.

## Correction 5 -- the kick's expected range needs anchoring on the actual pre-event baseline, not the blueprint's fixed nominal

**Finding:** a real, correctly-sized `course_correction_2` kick on
`thrust` was still flagged FAULT partway through, even with the new
size-aware expected-cause check active.

**Reason:** `sim/real_data_sources.py`'s SYNTHETIC noise sources
(`thrust` among them) are unbounded random walks with no mean
reversion -- by sample ~12,240 of a 21,600-sample run, `thrust`'s
baseline had drifted roughly 40 units away from its blueprint
nominal (500.0) purely from accumulated noise, the same underlying
fact Correction 1 already established (a random walk's spread grows
with the run's own length). The expected range was computed as
"nominal + the kick's own shape," which doesn't account for that
drift at all -- so a perfectly correctly-sized kick, riding on top of
a baseline that had wandered away from nominal, was wrongly judged
"outside its expected size."

**Fix:** `sim/run_sim_test.py`'s `active_expected_causes()` now
anchors each kick's expected value on the channel's ACTUAL reading
one second before the event started (`event_baselines()`), not the
blueprint's fixed nominal -- correctly separating "is the kick itself
the right size" (what this check should answer) from "has the
baseline drifted" (a true, accepted fact about these sensors,
already established, not this check's job to re-litigate).

**Verified:** re-ran the clean timeline after the fix -- the
`course_correction_2`/`thrust` false alarm is gone; 0/22 false alarms
on normal events confirmed again with all three fixes together.

## Checkpoint

Corrections 3, 4 and 5 applied; nothing else changed. No further
changes to `sim/blueprint.py`, `sim/rulebook.py` or
`sim/run_sim_test.py`'s expected-cause mechanism after this file's
checkpoint commit, whatever the faulted runs' results show.

# Third commissioning round -- Item C (28 October 2026)

Item C added a fault-class table (`sim/blueprint.py`'s `FAULT_CLASSES`,
five classes per sensor -- level/jump/leash_soft/leash_hard/
stillness) and wired EDEN to react to it, but added NO new numeric
blueprint/rule-book values -- level/jump/leash/Stillness limits are
byte-identical to the second round's frozen state. Re-ran the clean
timeline anyway, on principle (never assume a change is inert without
checking), before touching anything fault-related.

**Result: clean. Zero corrections needed.** 0/22 false alarms on
normal events, same as the second round's frozen state. Background
false alarms: `battery_voltage` 1,069 samples from sample 20,530 (was
1,070 in the first round -- a 1-sample difference, not a real change).
`fuel_flow` now shows only 600 samples from sample 13,514, where the
FIRST commissioning round (before `sim/human_signoff.py` existed)
reported 8,086 -- checked, not assumed: 13,514 + 8,086 = 21,600
exactly, meaning that first round's false latch ran continuously to
the very end of the timeline with nothing to ever release it.
`sim/human_signoff.py` (added in the SECOND round, Item 3b) now
correctly releases this same stray false latch after its stated
`HUMAN_RESPONSE_DELAY_SECONDS` (600.0s) once the human checks it
against the (empty, for a clean commissioning run) fault list and
finds nothing real there -- 600 samples matches that delay exactly.
This is human_signoff.py working correctly on an incidental false
latch, not a new defect and not something this round introduced;
flagged here because the raw number changed and deserves an honest
explanation, not silence.

## Checkpoint

No corrections this round. Frozen state (blueprint/rule book numbers,
unchanged; `FAULT_CLASSES`, new) committed before any fault run, same
discipline as every round so far.
