# sim/craft.py
# Added 2026-10-27 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Builds the simulated LEON craft's CLEAN timeline -- normal events
with their expected kicks, clean control stretches, NO faults at all
(faults are sim/fault_injection.py's job, a separate file that reads
this module but is never read BY it). One ~6-hour (21,600-sample,
1Hz) run, SCENARIO_SEED fixed and separate from
sim/blueprint.py's DERIVATION_SEED -- only the noise realisation ties
to the seed; the event schedule below is fixed, same discipline as
simulated_tests/leash_drift/'s PLANTED_EVENTS.

EVENT SHAPES:
- "kick" (engine_bay_temp, battery_current, thrust during a burn or
  correction): ramps up linearly over the event's duration, then
  ramps back down over an equal following period -- "fades into the
  background," per SPEC.md's Blueprint section.
- "jitter" (battery_voltage/battery_current during a battery switch):
  extra noise on top of the sensor's own baseline noise for the
  event's duration, no shape, no decay -- "known interference," not a
  kick.
- "zero" (solar_current during a solar occlusion): reads exactly 0 for
  the event's duration -- SPEC.md's "legitimately reads zero."
- "deltav": used only by sim/fault_injection.py's dying-battery fault
  (a genuinely permanent decline -- batteries don't recover). NOT used
  for velocity's burn reaction -- see sim/blueprint.py's
  "COMMISSIONING FINDING" comment on EVENT_EFFECTS for why.

Every magnitude is a fixed multiple of the affected sensor's own
blueprint-derived limit (KICK_MULTIPLE / JITTER_MULTIPLE /
DELTAV_MULTIPLE below) -- same EVENT_MULTIPLE discipline as
leash_drift, never tuned against any result.

Each event dict's "end_s" covers the FULL kick -- ramp AND decay
(start_s to start_s + 2*duration_s for a "kick" effect), not just the
ramp. COMMISSIONING FINDING: this is load-bearing, not cosmetic -- the
first version only recorded the ramp's end, so the expected-cause
window handed to GRACIE (sim/run_sim_test.py) closed while the kick
was still decaying, which GRACIE then saw as an unexplained crossing
and latched FAULT -- permanently, since nothing in this continuous
6-hour run ever calls clear_fault(). "jitter" and "zero" effects have
no decay tail, so their end_s is just start_s + duration_s.
"""
import random
from datetime import datetime, timedelta

from sim.blueprint import EVENT_EFFECTS
from sim.real_data_sources import SENSORS, build_noise_series

SCENARIO_SEED = 1               # fixed, separate from blueprint.DERIVATION_SEED
TOTAL_SECONDS = 21600            # ~6 hours, 1Hz
START_TIME = datetime(2026, 1, 1)

KICK_MULTIPLE = 8.0              # x the affected sensor's leash_slope_limit
JITTER_MULTIPLE = 6.0            # x the affected sensor's jump_limit
DELTAV_MULTIPLE = 400.0          # x velocity's leash_slope_limit (a real, lasting change)

# (event_name, kind, start_s, duration_s, scale) -- scale multiplies
# the *_MULTIPLE constants; course_correction uses a smaller/shorter
# scale than engine_burn, same links, per the approved plan.
EVENT_SCHEDULE = [
    ("engine_burn_1", "engine_burn", 1500, 120, 1.0),
    ("engine_burn_2", "engine_burn", 9500, 120, 1.0),
    ("course_correction_1", "course_correction", 3400, 40, 0.4),
    ("course_correction_2", "course_correction", 12200, 40, 0.4),
    ("battery_switch_1", "battery_switch", 5200, 30, 1.0),
    ("battery_switch_2", "battery_switch", 15800, 30, 1.0),
    ("solar_occlusion_1", "solar_occlusion", 7000, 300, 1.0),
    ("solar_occlusion_2", "solar_occlusion", 18200, 300, 1.0),
]


def _kick_offset(start_s, duration_s, peak, t):
    """Ramps 0 -> peak over [start, start+duration), then peak -> 0
    over the following equal-length window; 0 outside both."""
    if t < start_s:
        return 0.0
    if t < start_s + duration_s:
        return peak * (t - start_s) / duration_s
    decay_end = start_s + 2 * duration_s
    if t < decay_end:
        return peak * (decay_end - t) / duration_s
    return 0.0


def _deltav_offset(start_s, duration_s, peak, t):
    """Ramps 0 -> peak over [start, start+duration), then HOLDS peak
    forever after -- a real burn's lasting effect, not a kick."""
    if t < start_s:
        return 0.0
    if t < start_s + duration_s:
        return peak * (t - start_s) / duration_s
    return peak


def build_clean_timeline(rule_book, blueprint, seed=SCENARIO_SEED):
    """Returns (timestamps, values, events) -- values is
    {sensor_name: [v0, v1, ...]}; events is the EVENT_SCHEDULE above,
    each entry expanded to (name, kind, start_s, end_s,
    affected_channels) for run_sim_test.py's expected_causes and
    false-alarm scoring."""
    master_rng = random.Random(seed)
    sensor_seeds = {name: master_rng.random() for name in SENSORS}

    timestamps = [START_TIME + timedelta(seconds=i) for i in range(TOTAL_SECONDS)]
    values = {}
    for sensor_name, (nominal, _units) in SENSORS.items():
        rng = random.Random(sensor_seeds[sensor_name])
        noise = build_noise_series(sensor_name, TOTAL_SECONDS, rng)
        values[sensor_name] = [nominal + n for n in noise]

    # Extra jitter noise needs its own independent rng per (sensor,
    # event) so it isn't correlated with the baseline noise series.
    jitter_rng = random.Random(master_rng.random())

    events = []
    for name, kind, start_s, duration_s, scale in EVENT_SCHEDULE:
        affected = dict(EVENT_EFFECTS.get(kind, {}))
        max_end_s = start_s + duration_s  # grows to cover a kick's full decay, below

        for sensor_name, effect in affected.items():
            rule = rule_book[sensor_name]
            if effect == "kick":
                peak = scale * KICK_MULTIPLE * rule.leash_slope_limit * duration_s
                kick_end_s = start_s + 2 * duration_s
                max_end_s = max(max_end_s, kick_end_s)
                for t in range(start_s, min(kick_end_s, TOTAL_SECONDS)):
                    values[sensor_name][t] += _kick_offset(start_s, duration_s, peak, t)
            elif effect == "jitter":
                extra = scale * JITTER_MULTIPLE * rule.jump_limit
                for t in range(start_s, min(start_s + duration_s, TOTAL_SECONDS)):
                    values[sensor_name][t] += jitter_rng.uniform(-extra, extra)
            elif effect == "zero":
                for t in range(start_s, min(start_s + duration_s, TOTAL_SECONDS)):
                    values[sensor_name][t] = 0.0

        events.append({
            "name": name, "kind": kind, "start_s": start_s, "end_s": max_end_s,
            "affected_channels": sorted(affected.keys()),
        })

    return timestamps, values, events
