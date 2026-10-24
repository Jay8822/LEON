# simulated_tests/leash_drift/generate_leash_drift.py
# Added 2026-10-24 — Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Builds the SIMULATED leash-drift scenarios -- controlled-condition
test of the leash (drift-sense) mechanism itself, agreed with Jay
alongside the OPS-SAT leash extension (real_data_tests/opssat_ad/),
because OPS-SAT's own fragments turned out too short/spike-shaped to
exercise sustained drift at all (see that folder's README).

SIMULATED. Not real spacecraft data. Results here measure the leash
mechanism's sensitivity under known, planted conditions -- not
performance on a real spacecraft. Never mixed into the real-data
scorecards in real_data_tests/.

Design, agreed with Jay before building (updated 2026-10-24: the
leash itself was redefined by Jay from two slope-based limits to one
slope limit plus two durations, because soft/hard came out almost
identical as slopes and the test couldn't show them working
separately -- see SPEC.md's "Leash" section and
run_opssat_ad_test.py's module docstring):

- Normal wobble is built from REAL behaviour, not an invented noise
  model: consecutive-sample deltas are bootstrap-resampled (with
  replacement) from real OPSSAT-AD nominal training fragments, for one
  real channel at a time, restricted to that channel's 1-second-
  sampled fragments only (so every resampled delta is a real,
  1-second step actually seen on that channel). Deltas are de-meaned
  before resampling, so a clean control stretch has no net drift of
  its own by construction -- any apparent drift there is reported
  honestly as a false pull, not suppressed.
- Two channels, one of each real sensor type: CADC0872 (magnetometer)
  and CADC0894 (photodiode) -- checked first which channels actually
  have any 1-second-sampled data at all: of the 6 photodiode channels,
  only CADC0894 does (the other 5 are 5-second-sampled only), so it's
  the one usable photodiode source for this test.
- The leash's one slope limit is derived BEFORE any drift is planted,
  the same way as the OPS-SAT test: pure-noise chunks (no drift at
  all) are treated as fragments and fed through the same
  derive_leash_limits() used there. A fixed derivation seed (0) is
  used for this step, separate from every seed used for the actual
  scored scenario below, so limit derivation isn't tied to the same
  randomness being scored.
- Planted drifts are sized as fixed multiples of that already-derived
  limit (e.g. "5x the limit"), not as independently invented physical
  quantities. Since soft/hard is now about DURATION, not strength,
  every catchable event uses the same comfortable slope margin (5x the
  limit) -- what varies between events is how long each one lasts,
  chosen (empirically, while building this test fixture, not by
  tuning against any scored result) to land clearly on one side or the
  other of the soft/hard duration boundary.
- One ~2-hour (7,200 second) timeline per channel per seed, 1Hz, built
  once per (channel, seed) pair: clean control stretches (no added
  drift) alternating with six planted events -- below_soft (too brief
  to reach even the soft duration), soft_only (reaches soft, not hard,
  by holding at its new level forever), settles_back (reaches soft,
  then subsides back to normal before reaching hard -- the key case
  for "give it a chance to settle, escalate only if it doesn't go
  away on its own"), reaches_hard (reaches hard), tiny (below the
  slope limit entirely, expected to go uncaught regardless of
  duration), and returns (ramps past hard, then back to normal). Only
  the noise realisation varies with the seed; the event schedule and
  sizes are fixed.
"""

import csv
import os
import random
from datetime import datetime, timedelta

from real_data_tests.opssat_ad.run_opssat_ad_test import (
    Fragment,
    derive_leash_limits,
    LEASH_SLOPE_PCT,
)

OPSSAT_SEGMENTS_CSV = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..",
    "real_data_tests", "opssat_ad", "data", "segments.csv",
)

CHANNELS = ["CADC0872", "CADC0894"]

SIM_HZ = 1.0  # fixed: only sampling==1 real fragments are used as the delta source
TOTAL_SECONDS = 7200  # ~2 hours
DERIVATION_SEED = 0  # fixed, separate from every scenario seed below
DERIVATION_CHUNK_SECONDS = 300  # matches real data's median fragment duration
DERIVATION_N_CHUNKS = 30

# Comfortable margin above the single slope limit for every event
# that should register at all -- isolates "how long" from "how
# strong," since strength is no longer what distinguishes soft/hard.
EVENT_MULTIPLE = 5.0
TINY_MULTIPLE = 0.5  # below the limit entirely -- never starts a pull

# (name, start_s, duration_s, multiple, shape)
# shape is "ramp" (0 -> target, holds), or "return" (0 -> target -> 0,
# ramping up for the first half of duration_s, back down for the rest
# -- each half is its own windowed-slope episode, since the trailing
# window straddling the turnaround briefly cancels out, resetting the
# "continuous" run).
# Durations chosen (while building this fixture, not from any scored
# result) to land clearly on one side of the soft (60s) / hard (150s)
# duration boundary -- see module docstring.
PLANTED_EVENTS = [
    ("below_soft",    500,   20, EVENT_MULTIPLE, "ramp"),    # too brief for even soft
    ("soft_only",     1000,  100, EVENT_MULTIPLE, "ramp"),   # past soft, short of hard
    ("reaches_hard",  1600,  250, EVENT_MULTIPLE, "ramp"),   # past hard
    ("settles_back",  2000,  180, EVENT_MULTIPLE, "return"), # past soft, settles before hard -- each
                                                              # 90s half-phase clears soft, neither
                                                              # reaches hard's 150s on its own
    ("tiny",          2500,  300, TINY_MULTIPLE,  "ramp"),   # below the limit -- expected uncaught
    ("returns",       3300,  500, EVENT_MULTIPLE, "return"), # past hard, then back to normal
]
# Control stretches: every second of TOTAL_SECONDS not covered by a
# planted event above (0-500, 520-1000, 1100-1600, 1850-2000,
# 2180-2500, 2800-3300, 3800-7200).


def load_real_delta_pool(channel):
    """Real, 1-second-sampled, nominal, TRAINING consecutive-sample
    deltas for one channel -- the bootstrap source for simulated
    noise. Requires real_data_tests/opssat_ad/download_opssat_ad.py to
    have been run first."""
    if not os.path.exists(OPSSAT_SEGMENTS_CSV):
        raise SystemExit(
            f"{OPSSAT_SEGMENTS_CSV} not found -- run "
            "`python -m real_data_tests.opssat_ad.download_opssat_ad` first."
        )

    fragments = {}
    with open(OPSSAT_SEGMENTS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["channel"] != channel or row["train"] != "1" or row["label"] == "anomaly":
                continue
            if row["sampling"] != "1":
                continue
            seg_id = row["segment"]
            fragments.setdefault(seg_id, []).append(float(row["value"]))

    deltas = []
    for values in fragments.values():
        deltas.extend(values[i + 1] - values[i] for i in range(len(values) - 1))

    if not deltas:
        raise RuntimeError(f"no 1-second nominal training deltas found for {channel}")

    mean = sum(deltas) / len(deltas)
    return [d - mean for d in deltas]  # de-meaned -- see module docstring


def _build_noise_series(delta_pool, n_samples, rng):
    """A single bootstrap-resampled random walk, n_samples long,
    starting at 0."""
    values = [0.0]
    for _ in range(n_samples - 1):
        values.append(values[-1] + rng.choice(delta_pool))
    return values


def _make_fragment_from_series(values, start_time=None):
    start_time = start_time or datetime(2000, 1, 1)
    timestamps = [start_time + timedelta(seconds=i) for i in range(len(values))]
    frag = Fragment(segment_id="sim", channel="sim", anomalous=False, is_train=True)
    frag.values = values
    frag.timestamps = timestamps
    return frag


def derive_limit_for_channel(channel, delta_pool):
    """Pure-noise chunks, no drift at all, fed through the exact same
    derive_leash_limits() the real OPS-SAT test uses -- see module
    docstring. Fixed derivation seed, independent of any scenario
    seed. One limit now, not a soft/hard pair."""
    rng = random.Random(DERIVATION_SEED)
    chunks = []
    for _ in range(DERIVATION_N_CHUNKS):
        values = _build_noise_series(delta_pool, DERIVATION_CHUNK_SECONDS, rng)
        frag = _make_fragment_from_series(values)
        frag.channel = channel
        chunks.append(frag)

    limits = derive_leash_limits(chunks, LEASH_SLOPE_PCT)
    return limits[channel]["limit"]


def _event_offset(start_s, duration_s, shape, slope, t):
    """The planted drift's added offset at second `t`, in value-units.
    "ramp": a steady slope from the event's start, holding at its
    final level afterward (a real sustained drift that's never
    corrected doesn't snap back). "return": ramps up for the first
    half of the duration, then back down to exactly zero by the end --
    the planted "returns to normal on its own" case."""
    if shape == "ramp":
        if t < start_s:
            return 0.0
        elapsed = min(t - start_s, duration_s)
        return slope * elapsed
    if shape == "return":
        if t < start_s or t >= start_s + duration_s:
            return 0.0
        half = duration_s / 2.0
        elapsed = t - start_s
        return slope * elapsed if elapsed <= half else slope * (duration_s - elapsed)
    raise ValueError(f"unknown shape {shape!r}")


def build_scenario(channel, delta_pool, limit, seed):
    """One ~2-hour simulated timeline for `channel`, with the fixed
    planted events added on top of bootstrap noise. Returns
    (timestamps, values, events) where events is a list of dicts with
    name/start_s/end_s/target_slope/shape/expected_soft/expected_hard."""
    rng = random.Random(seed)
    values = _build_noise_series(delta_pool, TOTAL_SECONDS, rng)

    events = []
    for name, start_s, duration_s, multiple, shape in PLANTED_EVENTS:
        slope = limit * multiple
        end_s = start_s + duration_s
        for t in range(start_s, min(end_s, TOTAL_SECONDS)):
            values[t] += _event_offset(start_s, duration_s, shape, slope, t)
        events.append({
            "name": name, "start_s": start_s, "end_s": end_s,
            "target_slope": slope, "shape": shape,
            # By design (see module docstring): below_soft is too
            # brief for even soft; soft_only and settles_back reach
            # soft but not hard (settles_back specifically tests "give
            # it a chance to settle" -- it subsides before hard);
            # reaches_hard and returns both reach hard; tiny is below
            # the limit entirely, so it's never even a pull.
            "expected_soft": name in ("soft_only", "settles_back", "reaches_hard", "returns"),
            "expected_hard": name in ("reaches_hard", "returns"),
        })

    start_time = datetime(2000, 1, 1)
    timestamps = [start_time + timedelta(seconds=i) for i in range(TOTAL_SECONDS)]
    return timestamps, values, events
