# sim/fault_injection.py
# Added 2026-10-27 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Plants the four agreed faults onto a COPY of sim/craft.py's clean
timeline. Separate from blueprint.py/rulebook.py/craft.py on purpose
-- it reads their output but is never read BY them, and was written
without reference to how the clean timeline "wants" to be gamed (the
clean timeline and the frozen rule book were committed to git before
this file was written at all -- see sim/COMMISSIONING.md).

FOUR FAULTS, each once, non-overlapping with every normal event and
each other:

1. DYING BATTERY (battery_voltage, start=400s, duration=2700s/45min):
   ramps down linearly, then HOLDS the low value permanently --
   batteries don't recover. HONEST NOTE: the approved plan called for
   this to be sourced from NASA's real Li-ion Battery Aging Dataset;
   that dataset turned out to be unreachable from this machine (see
   sim/real_data_sources.py's module docstring) -- this is a
   SYNTHETIC monotonic decay instead, sized as a fixed multiple of
   battery_voltage's own derived level/leash limits, same discipline
   as every other planted event, not a real measured curve.
2. STUCK SENSOR (attitude_rate, start=10200s, duration=1800s/30min):
   frozen at its exact value from the instant before the fault starts
   -- no crossing, no jump, by construction. This is DELIBERATE and
   is exactly the finding Jay asked to see reported plainly (approved
   change 4): a frozen sensor is invisible to level/jump/leash, which
   all look for MOVEMENT past a limit, not absence of movement.
3. NOISY SENSOR (fuel_flow, start=13000s, duration=1800s/30min): extra
   zero-mean jitter on top of the existing noise, widening the spread
   with NO mean shift -- the direct analogue of the "noisier, not
   drifting" question from real_data_tests/esa_adb/CHECKS.md 2a,
   planted here as a KNOWN case instead of inferred.
4. BAD ENGINE BURN (engine_bay_temp/battery_current/thrust/velocity,
   start=20000s, duration=120s): a THIRD burn-like event, scaled
   UNIFORMLY to WRONG_BURN_SCALE (0.25) across every normally-reactive
   channel, instead of the normal 1.0. Every affected sensor moves
   together, consistently, exactly as a real (if underpowered) burn
   would -- there is nothing internally inconsistent to notice. The
   only way to know it's wrong is to know the INTENDED size, which no
   sensor reports and which expected_causes (a channel-name set, not
   a magnitude) cannot carry either -- approved change 4's second
   example, and exactly what the Diagnostic checklist (not built yet)
   is for.
"""
import random

from sim.craft import _kick_offset, _deltav_offset

DYING_BATTERY_START, DYING_BATTERY_DURATION = 400, 2700
STUCK_SENSOR_START, STUCK_SENSOR_DURATION = 10200, 1800
NOISY_SENSOR_START, NOISY_SENSOR_DURATION = 13000, 1800
BAD_BURN_START, BAD_BURN_DURATION = 20000, 120
WRONG_BURN_SCALE = 0.25

DYING_BATTERY_DECAY_MULTIPLE = 6.0   # x (nominal - level_low)
NOISY_SENSOR_WIDEN_MULTIPLE = 5.0    # x jump_limit, zero-mean extra jitter

FAULT_RNG_SEED = 99  # fixed, independent of SCENARIO_SEED and DERIVATION_SEED

# Item 3b re-testing (Jay: "fresh seeds ... with new fault timings"):
# each fault's start time can be jittered by up to this many seconds,
# seeded separately from FAULT_RNG_SEED's own noise-jitter use above,
# so "same seed" runs (timing_seed=None) reproduce the original
# round's exact placement byte-for-byte.
FAULT_TIMING_JITTER_SECONDS = 3000
_FAULT_BASE_SCHEDULE = [
    ("dying_battery", DYING_BATTERY_START, DYING_BATTERY_DURATION, ("battery_voltage",)),
    ("stuck_sensor", STUCK_SENSOR_START, STUCK_SENSOR_DURATION, ("attitude_rate",)),
    ("noisy_sensor", NOISY_SENSOR_START, NOISY_SENSOR_DURATION, ("fuel_flow",)),
    ("bad_engine_burn", BAD_BURN_START, BAD_BURN_DURATION,
     ("engine_bay_temp", "battery_current", "thrust", "velocity")),
]


def _overlaps(a_start, a_end, b_start, b_end):
    return a_start < b_end and b_start < a_end


def _pick_fault_starts(events, total_seconds, timing_seed):
    """{fault_name: start_s}. timing_seed=None reproduces the original
    fixed schedule exactly. Otherwise, each fault's start is jittered
    within +/-FAULT_TIMING_JITTER_SECONDS of its base position,
    retried against a fresh candidate (up to 50 tries, falling back
    to the base position if none is found) until it doesn't overlap,
    on a shared channel, any normal event or any OTHER fault already
    placed this call -- same "non-overlapping" guarantee the fixed
    schedule's own module docstring already states, just checked
    rather than hand-verified for a new seed."""
    if timing_seed is None:
        return {name: start for name, start, _duration, _channels in _FAULT_BASE_SCHEDULE}

    rng = random.Random(timing_seed)
    placed = []  # (start, end, channels)
    starts = {}
    for name, base_start, duration, channels in _FAULT_BASE_SCHEDULE:
        chosen = base_start
        for _ in range(50):
            lo = max(0, base_start - FAULT_TIMING_JITTER_SECONDS)
            hi = min(total_seconds - duration, base_start + FAULT_TIMING_JITTER_SECONDS)
            candidate = rng.randint(lo, hi)
            end = candidate + duration
            conflict = any(
                set(channels) & set(ev["affected_channels"])
                and _overlaps(candidate, end, ev["start_s"], ev["end_s"])
                for ev in events
            ) or any(
                set(channels) & set(p_channels) and _overlaps(candidate, end, p_start, p_end)
                for p_start, p_end, p_channels in placed
            )
            if not conflict:
                chosen = candidate
                break
        placed.append((chosen, chosen + duration, channels))
        starts[name] = chosen
    return starts


def inject_faults(timestamps, clean_values, rule_book, total_seconds, events=None, timing_seed=None):
    """Returns (values, faults) -- values is a NEW dict (clean_values
    is not mutated), faults is ground truth: [{"name", "channel",
    "start_s", "end_s", "kind"}]. `events` (the normal schedule) is
    only needed when timing_seed is not None, to keep a re-randomized
    fault clear of normal events on the same channel(s)."""
    values = {name: list(series) for name, series in clean_values.items()}
    rng = random.Random(FAULT_RNG_SEED)
    starts = _pick_fault_starts(events or [], total_seconds, timing_seed)
    faults = []

    # 1. Dying battery -- synthetic decay (see module docstring).
    rule = rule_book["battery_voltage"]
    decay_magnitude = DYING_BATTERY_DECAY_MULTIPLE * (rule.level_high - rule.level_low) / 2.0
    start_s = starts["dying_battery"]
    end_s = start_s + DYING_BATTERY_DURATION
    for t in range(start_s, total_seconds):
        values["battery_voltage"][t] -= _deltav_offset(
            start_s, DYING_BATTERY_DURATION, decay_magnitude, t
        )
    faults.append({"name": "dying_battery", "channel": "battery_voltage",
                    "start_s": start_s, "end_s": end_s, "kind": "dying_battery"})

    # 2. Stuck sensor -- frozen at its last real value.
    start_s = starts["stuck_sensor"]
    frozen_value = values["attitude_rate"][start_s - 1]
    end_s = start_s + STUCK_SENSOR_DURATION
    for t in range(start_s, min(end_s, total_seconds)):
        values["attitude_rate"][t] = frozen_value
    faults.append({"name": "stuck_sensor", "channel": "attitude_rate",
                    "start_s": start_s, "end_s": end_s, "kind": "stuck_sensor"})

    # 3. Noisy sensor -- extra zero-mean jitter, no mean shift.
    rule = rule_book["fuel_flow"]
    extra = NOISY_SENSOR_WIDEN_MULTIPLE * rule.jump_limit
    start_s = starts["noisy_sensor"]
    end_s = start_s + NOISY_SENSOR_DURATION
    for t in range(start_s, min(end_s, total_seconds)):
        values["fuel_flow"][t] += rng.uniform(-extra, extra)
    faults.append({"name": "noisy_sensor", "channel": "fuel_flow",
                    "start_s": start_s, "end_s": end_s, "kind": "noisy_sensor"})

    # 4. Bad engine burn -- same KICK shape as a normal burn (see
    # sim/blueprint.py's EVENT_EFFECTS comment on why velocity is a
    # kick, not a permanent step, this round), wrong scale, uniformly
    # across every normally-reactive channel. end_s covers the full
    # decay tail, same reasoning as sim/craft.py's events.
    from sim.craft import KICK_MULTIPLE
    bad_burn_channels = ("engine_bay_temp", "battery_current", "thrust", "velocity")
    start_s = starts["bad_engine_burn"]
    kick_end = start_s + 2 * BAD_BURN_DURATION
    for channel in bad_burn_channels:
        rule = rule_book[channel]
        peak = WRONG_BURN_SCALE * KICK_MULTIPLE * rule.leash_slope_limit * BAD_BURN_DURATION
        for t in range(start_s, min(kick_end, total_seconds)):
            values[channel][t] += _kick_offset(start_s, BAD_BURN_DURATION, peak, t)
    faults.append({"name": "bad_engine_burn", "channel": ",".join(sorted(bad_burn_channels)),
                    "start_s": start_s, "end_s": kick_end, "kind": "bad_engine_burn",
                    "wrong_scale": WRONG_BURN_SCALE})

    return values, faults
