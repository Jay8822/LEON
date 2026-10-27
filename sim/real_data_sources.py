# sim/real_data_sources.py
# Added 2026-10-27 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Real and synthetic noise sources for the simulated LEON craft's nine
sensors (Item 3 of the 27 October 2026 round).

HONEST NOTE ON THE BATTERY DATASET -- A REAL DEVIATION FROM THE
APPROVED PLAN, NOT A SHORTCUT: the approved plan called for
battery_voltage/battery_current, and the dying-battery fault, to be
sourced from NASA's real Li-ion Battery Aging Dataset. Checked for
real, from this machine, before giving up on it: NASA's usual host for
it (DASHlink / c3.nasa.gov/dashlink) timed out on every attempt;
data.nasa.gov's own catalog page for it is metadata only, with no
working direct file link found; the known mirrors (IEEE DataPort,
Kaggle) both require creating an account, which this project avoids
doing without asking first (same rule as the SatNOGS note elsewhere in
Ccode update.txt). This is a genuine access obstacle hit while
building, reported plainly rather than silently worked around --
Jay should decide whether it's worth chasing further (e.g. requesting
an account be created, or another source). For THIS round,
battery_voltage/battery_current and the dying-battery fault use an
honestly-labelled SYNTHETIC model instead -- same discipline already
used for thrust/fuel_flow, which never had a real analogue to begin
with. Flagged again in sim/RESULTS.md and Ccode update.txt.

REAL SOURCE (unaffected by the above): solar_current, engine_bay_temp,
avionics_bay_temp, velocity and attitude_rate all bootstrap from the
two real, 1Hz-sampled OPS-SAT channels this project has already
validated as usable this way -- CADC0872 (magnetometer) and CADC0894
(photodiode); see simulated_tests/leash_drift/generate_leash_drift.py
's own docstring for why only these two OPSSAT-AD channels have usable
1Hz nominal-training data at all. This grounds real sample-to-sample
NOISE CHARACTER, not a physical analogy -- solar_current's pairing
with CADC0894 (a real light sensor) is the one place source and
subject happen to match; the other four pairings are noise-character
grounding only, stated plainly, never claimed as a thermal or motion
analogue.

SYNTHETIC (battery_voltage, battery_current, thrust, fuel_flow):
plain bounded random-walk jitter, fixed step scale per sensor, no real
data behind it at all -- stated everywhere this appears.

Every noise source here is a SIMULATED test fixture (same category as
simulated_tests/leash_drift/'s own values) -- fixed step scales and
nominal baselines are illustrative design choices for this
proof-of-concept, not calibrated to any real craft.
"""
import os
import random

from real_data_tests.opssat_ad.run_opssat_ad_test import Fragment
from simulated_tests.leash_drift.generate_leash_drift import load_real_delta_pool

# (sensor_name, nominal_baseline, units) -- nominal values are
# illustrative, not calibrated to any real craft (module docstring).
SENSORS = {
    "battery_voltage": (28.0, "V"),
    "battery_current": (4.0, "A"),
    "solar_current": (6.0, "A"),
    "engine_bay_temp": (22.0, "C"),
    "avionics_bay_temp": (18.0, "C"),
    "thrust": (500.0, "N"),
    "fuel_flow": (0.2, "kg/s"),
    "velocity": (7500.0, "m/s"),
    "attitude_rate": (0.0, "deg/s"),
}

# Real-noise-character source channel, for the five sensors that have
# one. The other four (battery_voltage, battery_current, thrust,
# fuel_flow) are SYNTHETIC -- see module docstring.
REAL_NOISE_SOURCE = {
    "solar_current": "CADC0894",
    "engine_bay_temp": "CADC0894",
    "avionics_bay_temp": "CADC0872",
    "velocity": "CADC0872",
    "attitude_rate": "CADC0872",
}

# Fixed step scale for each SYNTHETIC sensor's bounded random-walk
# jitter -- a design choice, not derived from any data (there is none
# to derive it from). Picked so each sensor's resulting noise is a
# small fraction of its nominal baseline, same spirit as real sensor
# noise being small relative to the signal.
SYNTHETIC_STEP_SCALE = {
    "battery_voltage": 0.01,     # ~0.04% of nominal per sample
    "battery_current": 0.02,
    "thrust": 1.0,
    "fuel_flow": 0.0005,
}

_delta_pool_cache = {}


def real_delta_pool(opssat_channel):
    """De-meaned, real, 1-second-sampled, nominal TRAINING
    consecutive-sample deltas for one OPS-SAT channel -- cached, since
    several sim sensors share the same two source channels and this
    machine has 6GB of RAM (loading it twice would be wasteful, not
    unsafe, but there's no reason to)."""
    if opssat_channel not in _delta_pool_cache:
        _delta_pool_cache[opssat_channel] = load_real_delta_pool(opssat_channel)
    return _delta_pool_cache[opssat_channel]


def build_real_noise_series(opssat_channel, n_samples, rng):
    """A bootstrap-resampled random walk, n_samples long, starting at
    0 -- same method as leash_drift's _build_noise_series()."""
    pool = real_delta_pool(opssat_channel)
    values = [0.0]
    for _ in range(n_samples - 1):
        values.append(values[-1] + rng.choice(pool))
    return values


def build_synthetic_noise_series(sensor_name, n_samples, rng):
    """Bounded uniform random-walk jitter, starting at 0 -- no real
    data behind this at all (module docstring)."""
    step_scale = SYNTHETIC_STEP_SCALE[sensor_name]
    values = [0.0]
    for _ in range(n_samples - 1):
        values.append(values[-1] + rng.uniform(-step_scale, step_scale))
    return values


def build_noise_series(sensor_name, n_samples, rng):
    """Dispatches to the real or synthetic source for this sensor,
    per REAL_NOISE_SOURCE above."""
    if sensor_name in REAL_NOISE_SOURCE:
        return build_real_noise_series(REAL_NOISE_SOURCE[sensor_name], n_samples, rng)
    return build_synthetic_noise_series(sensor_name, n_samples, rng)


def make_fragment(sensor_name, values, timestamps, is_train=True, anomalous=False):
    """Wraps a plain (values, timestamps) series as a Fragment, reusing
    real_data_tests/opssat_ad/run_opssat_ad_test.py's own derivation
    functions (derive_thresholds/derive_jump_limits/derive_leash_limits)
    rather than reinventing percentile derivation."""
    frag = Fragment(segment_id="sim", channel=sensor_name, anomalous=anomalous, is_train=is_train)
    frag.values = values
    frag.timestamps = timestamps
    return frag
