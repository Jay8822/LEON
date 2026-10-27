# sim/blueprint.py
# Added 2026-10-27 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""The simulated LEON craft's BLUEPRINT (Item 3, 27 October 2026
round) -- SPEC.md's "Blueprint (stack-wide)" section, built for a
craft where the truth is known. Nine sensors (see
sim/real_data_sources.py's SENSORS): battery_voltage, battery_current,
solar_current, engine_bay_temp, avionics_bay_temp, thrust, fuel_flow,
velocity, attitude_rate.

CO-DESIGNED WITH THE RULE BOOK (sim/rulebook.py), THEN FROZEN, per
Jay's clarification: whoever builds a system has to know exactly what
it's expected to do, so design and limits inform each other -- that's
craftsmanship, not cheating. What's NOT allowed, and not done here: any
change to this file or rulebook.py after seeing any faulted-run result.
sim/COMMISSIONING.md is the one place corrections happen, BEFORE
fault_injection.py exists, each one written down with its reason.

NOISE AND LIMIT DERIVATION: each sensor's level/jump/leash limits are
derived from several CLEAN noise-only fragments (no event, no fault),
built with DERIVATION_SEED -- a fixed seed, separate from
SCENARIO_SEED (the one real scored run uses) -- through
real_data_tests/opssat_ad/run_opssat_ad_test.py's own
derive_thresholds()/derive_jump_limits()/derive_leash_limits(), reused
rather than reinvented (same method
simulated_tests/leash_drift/generate_leash_drift.py already uses for
its own single leash limit). STRICT-style percentiles throughout
(95th/5th for level, 95th for jump, 99th for leash slope) -- one fixed
setting, not STRICT-vs-LOOSE, since this sim isn't testing that
question.

LEASH DURATIONS: window=30s, soft=60s, hard=150s -- reused directly
from real_data_tests/opssat_ad/run_opssat_ad_test.py's own leash test
fixture values (LEASH_WINDOW_SECONDS/SOFT/HARD_DURATION_SECONDS),
explicitly NOT hardware-calibrated, same as that module already says
about them.

EXPECTED KICKS AND KNOWN INTERFERENCE (the cause-and-effect links,
exactly as agreed with Jay):
- Engine burn / course correction (course correction uses the same
  links, BURN_KICK_SCALE smaller and shorter -- see sim/craft.py):
  engine_bay_temp gets an expected kick (ramps up during the event,
  decays after); battery_current gets an expected kick (rises during
  the event); velocity changes by the event's intended delta-v (the
  event's primary intended effect, not a "kick" -- navigation's normal
  job).
- Battery switch: battery_voltage and battery_current jitter more than
  normal for the event's duration (known interference -- noisier, not
  a settle-back shape); avionics_bay_temp is DELIBERATELY unaffected
  -- the "related sensor did NOT move" control case.
- Solar occlusion: solar_current reads an expected zero for the
  event's duration (SPEC.md's "sensors that legitimately read zero in
  some conditions"); nothing else is affected.

Kick/jitter magnitudes are sized as fixed multiples of each affected
sensor's OWN derived limit (leash slope limit for a ramping kick,
jump limit for jitter) -- same discipline as leash_drift's
EVENT_MULTIPLE, never tuned against any result. See sim/craft.py for
the actual multiples and the full event schedule.
"""
import random
from datetime import datetime, timedelta

from real_data_tests.opssat_ad.run_opssat_ad_test import (
    derive_thresholds, derive_jump_limits, derive_leash_limits,
)
from sim.real_data_sources import SENSORS, build_noise_series, make_fragment

DERIVATION_SEED = 0          # fixed, separate from SCENARIO_SEED
# MUST match sim/craft.py's TOTAL_SECONDS (21,600 -- not imported
# directly to avoid a circular import; duplicated and documented
# instead). COMMISSIONING FINDING (sim/COMMISSIONING.md): a random
# walk's spread grows with sqrt(duration) -- deriving bounds from the
# original 300-second chunks (copied from leash_drift's much shorter,
# ~2-hour-total precedent without checking the duration match) and
# then scoring against this sim's full ~6-hour run left the walk with
# ~8.5x more room to wander than the bounds were calibrated for, so
# EVERY channel, including ones no event ever touches, drifted past
# its own level/leash line within the first few hundred to few
# thousand samples and stayed latched for virtually the whole run.
# Fixed by deriving from chunks the same length as the scored run --
# the same practice real_data_tests/esa_adb/ and opssat_ad/ already
# use (training chunks comparable in length to what they're later
# tested against), which this file should have followed from the
# start instead of copying leash_drift's chunk length unchecked.
DERIVATION_CHUNK_SECONDS = 21600
DERIVATION_N_CHUNKS = 20

LEASH_WINDOW_SECONDS = 30.0
LEASH_SOFT_DURATION_SECONDS = 60.0
LEASH_HARD_DURATION_SECONDS = 150.0

LEVEL_HIGH_PCT, LEVEL_LOW_PCT = 95, 5
JUMP_PCT = 95
LEASH_SLOPE_PCT = 99

# Which sensors each event kind affects, and how (module docstring).
# "kick" = engine_bay_temp/battery_current's ramp-and-decay shape;
# "jitter" = battery_voltage/battery_current's noisier-but-no-shape
# interference; "zero" = solar_current's expected-zero read.
EVENT_EFFECTS = {
    # thrust and velocity are deliberately included here (a documented
    # extension of the approved link list, not in the original list
    # verbatim): without SOME reaction on the thrust channel, "thrust"
    # would be a meaningless sensor in this sim -- it has to carry the
    # burn's own commanded magnitude, which is exactly what the bad-
    # engine-burn fault (sim/fault_injection.py) gets wrong.
    #
    # COMMISSIONING FINDING (sim/COMMISSIONING.md): velocity's reaction
    # was originally modelled as a PERMANENT step (a real burn's
    # delta-v genuinely doesn't decay back) rather than a kick. That
    # collided with GRACIE's current design: expected_causes only ever
    # suppresses the MOMENT of crossing, it has no way to redefine
    # "nominal" afterward -- that's what SPEC.md's Ageing mechanism is
    # for (a slow, human-signed-off baseline update), and Ageing isn't
    # exercised this round. A permanent velocity step therefore stayed
    # latched FAULT forever after the first burn, which isn't a
    # blueprint/rule-book numbers problem to fix -- it's a scope
    # mismatch. Changed velocity to a temporary KICK, same shape as
    # the other reactive sensors, for this round -- narrowing the sim
    # to what GRACIE's current design can actually represent, not
    # claiming a real burn's delta-v is temporary.
    "engine_burn": {"engine_bay_temp": "kick", "battery_current": "kick", "thrust": "kick", "velocity": "kick"},
    "course_correction": {"engine_bay_temp": "kick", "battery_current": "kick", "thrust": "kick", "velocity": "kick"},
    "battery_switch": {"battery_voltage": "jitter", "battery_current": "jitter"},
    "solar_occlusion": {"solar_current": "zero"},
}


def _build_derivation_series(sensor_name, rng):
    """DERIVATION_N_CHUNKS clean fragments, DERIVATION_CHUNK_SECONDS
    each, 1Hz, from this sensor's noise source -- same shape as
    leash_drift's derive_limit_for_channel(), generalised to also
    derive level/jump, not just leash."""
    fragments = []
    start_time = datetime(2000, 1, 1)
    for _ in range(DERIVATION_N_CHUNKS):
        n = int(DERIVATION_CHUNK_SECONDS)
        values = build_noise_series(sensor_name, n, rng)
        timestamps = [start_time + timedelta(seconds=i) for i in range(n)]
        fragments.append(make_fragment(sensor_name, values, timestamps))
    return fragments


def derive_blueprint(derivation_seed=DERIVATION_SEED):
    """Returns {sensor_name: {"nominal", "units", "level_high",
    "level_low", "jump_limit", "leash_slope_limit"}} -- the blueprint's
    derived numbers, one fixed seed, reused identically by
    sim/rulebook.py to build GRACIE's rule book."""
    rng = random.Random(derivation_seed)
    blueprint = {}
    for sensor_name, (nominal, units) in SENSORS.items():
        fragments = _build_derivation_series(sensor_name, rng)
        thresholds = derive_thresholds(fragments, LEVEL_HIGH_PCT, LEVEL_LOW_PCT)[sensor_name]
        jump = derive_jump_limits(fragments, JUMP_PCT)[sensor_name]
        leash = derive_leash_limits(fragments, LEASH_SLOPE_PCT)[sensor_name]
        blueprint[sensor_name] = {
            "nominal": nominal,
            "units": units,
            "level_high": nominal + thresholds["high"],
            "level_low": nominal + thresholds["low"],
            "jump_limit": jump["limit"],
            "leash_slope_limit": leash["limit"],
        }
    return blueprint
