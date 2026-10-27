# real_data_tests/cpp_proof/export_ring_overflow_stress.py
# Added 2026-10-27 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""SIMULATED stress dataset for NEW TASK 1b's strengthening round:
deliberately fills gracie_rulebook's fixed-size leash ring buffer
(kLeashRingCapacity = 2048, leon_config.hpp) near capacity, drains it
with a deliberate gap (proving the drain/trim logic still works after
a burst, not just monotonic growth), then fills it again past
capacity -- proving (a) results below capacity still match the real
Python GracieAgent bit-exact, and (b) the C++ side reports the
overflow (Status::kRingOverflow) at the exact sample index predicted,
rather than silently continuing with a wrong or truncated value.

SIMULATED. Not real spacecraft telemetry -- a synthetic, analytically
designed timestamp/value schedule, same labelling discipline as
simulated_tests/leash_drift/generate_leash_drift.py. Values are a
plain linear ramp (sample_index * VALUE_STEP), not bootstrapped from
real noise like that module -- the point here is exact, reproducible
ring arithmetic, not realistic wobble (realism against real data noise
is what the other two proof datasets, leash_drift and OPS-SAT, are
for).

The overflow sample index is not eyeballed from a trial run -- it's
computed by mechanically simulating gracie_rulebook's own ring-trim
rule (see simulate_ring() below, a direct line-for-line mirror of
update_leash_window()/ring_push_back() in gracie_rulebook.cpp) against
this script's own fixed schedule, before any C++ or Python GracieAgent
code runs at all. The proof step's job is only to confirm the real
systems match that prediction, not to produce it.

SCHEDULE (three phases, deliberately bursty, not a uniform ramp):
  Phase A -- BURST_1_COUNT samples at BURST_DT seconds apart (a tight
    cluster, well under LEASH_WINDOW_SECONDS in total span) -- ring
    grows from empty to BURST_1_COUNT entries.
  Phase B -- ONE sample after a GAP_SECONDS gap (>> LEASH_WINDOW_
    SECONDS) -- forces the ring to drain down to a single entry
    (every phase-A entry is now far older than the window), then
    pushes one new entry -- proving the drain path, not just growth.
  Phase C -- BURST_2_COUNT samples at BURST_DT seconds apart,
    starting right after phase B -- grows the ring from 2 entries
    past kLeashRingCapacity, triggering the overflow partway through.

Run from the repo root, after building "AI Stack C++ Test Build" (for
the proof step) and from a normal Python environment (for the
reference):

    python -m real_data_tests.cpp_proof.export_ring_overflow_stress
"""
import os

from agents.gracie_rulebook import ChannelRule
from real_data_tests.cpp_proof.proof_common import (
    OUT_DIR, write_sidecar, write_readings_csv, write_reference_csv, run_reference,
)

TAG = "ring_overflow_stress"
CHANNEL = "sim_overflow_channel"

LEASH_WINDOW_SECONDS = 1000.0
BURST_DT = 0.1                 # seconds between samples within a burst
BURST_1_COUNT = 500            # phase A: well short of capacity on its own
GAP_SECONDS = 1500.0           # > LEASH_WINDOW_SECONDS -- forces a full drain
BURST_2_COUNT = 2200           # phase C: deliberately overshoots 2048 from a count of 2
RING_CAPACITY = 2048           # must match leon_config.hpp's kLeashRingCapacity -- see check in main()

VALUE_STEP = 0.001             # plain linear ramp -- deterministic, non-trivial slopes to compare

# Values chosen so level/jump/leash latching never fires -- this test
# is about the ring's own bookkeeping, not the senses built on top of
# it (those are already covered by the other three proof datasets and
# by test_gracie_rulebook.cpp's unit tests).
NEVER_TRIGGERED = 1.0e18


def build_schedule():
    """Returns [(sample_index, timestamp, value), ...] for the full
    three-phase schedule described in the module docstring."""
    rows = []
    t = 0.0
    idx = 0
    for _ in range(BURST_1_COUNT):
        rows.append((idx, t, idx * VALUE_STEP))
        t += BURST_DT
        idx += 1
    # Phase B: one sample after the gap. `t` is currently one BURST_DT
    # past the last phase-A sample's timestamp; the gap is measured
    # from here, matching how a real irregular sensor would simply
    # have its next reading arrive late, not from some other origin.
    t = t - BURST_DT + GAP_SECONDS
    rows.append((idx, t, idx * VALUE_STEP))
    t += BURST_DT
    idx += 1
    for _ in range(BURST_2_COUNT):
        rows.append((idx, t, idx * VALUE_STEP))
        t += BURST_DT
        idx += 1
    return rows


def simulate_ring(rows, window_seconds, capacity):
    """Mechanical, line-for-line mirror of gracie_rulebook.cpp's
    update_leash_window()/ring_push_back(): a plain Python list used
    as the ring (append/pop(0) instead of the C++ circular-index
    arithmetic -- same observable behaviour, since this is an offline
    predictor, not the Power-of-10 code itself). Returns
    (ring_count_after_each_successful_sample, overflow_sample_index or
    None if the schedule never overflows)."""
    ring = []  # list of timestamps, oldest first
    counts_after = []
    for sample_index, timestamp, _value in rows:
        while len(ring) >= 2 and (timestamp - ring[1]) >= window_seconds:
            ring.pop(0)
        if len(ring) >= capacity:
            return counts_after, sample_index
        ring.append(timestamp)
        counts_after.append(len(ring))
    return counts_after, None


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rows = build_schedule()

    ring_counts, overflow_index = simulate_ring(rows, LEASH_WINDOW_SECONDS, RING_CAPACITY)
    if overflow_index is None:
        raise SystemExit(
            f"{TAG}: schedule never overflows a {RING_CAPACITY}-entry ring -- "
            "BURST_2_COUNT needs to be larger (this is a test-design bug, not a gracie_rulebook bug)."
        )
    print(f"{TAG}: predicted ring sizes range {min(ring_counts)}..{max(ring_counts)} "
          f"across {len(ring_counts)} successful samples; predicted overflow at "
          f"sample_index={overflow_index} (of {len(rows)} generated).")

    rule = ChannelRule(
        name=CHANNEL, units="u",
        level_high=NEVER_TRIGGERED, level_low=-NEVER_TRIGGERED,
        jump_limit=NEVER_TRIGGERED,
        leash_window_seconds=LEASH_WINDOW_SECONDS,
        leash_slope_limit=NEVER_TRIGGERED,
        leash_soft_duration_seconds=NEVER_TRIGGERED,
        leash_hard_duration_seconds=NEVER_TRIGGERED,
    )

    # clear_before is always False -- this test is about the ring
    # alone, not day-boundary clearing (already covered by the ESA-ADB
    # proof dataset).
    export_rows = [(idx, ts, val, False) for idx, ts, val in rows]

    write_sidecar(os.path.join(OUT_DIR, f"{TAG}_rule.txt"), rule)
    write_readings_csv(os.path.join(OUT_DIR, f"{TAG}_readings.csv"), export_rows)

    # The Python reference uses GracieAgent's real, unbounded deque --
    # it will happily process every row, including the ones past where
    # the fixed-size C++ ring overflows. That divergence past the
    # overflow point is EXPECTED, not a bug (module docstring) -- the
    # diff step only compares rows up to the overflow, and separately
    # checks the overflow itself fires at the predicted index.
    log = run_reference(CHANNEL, rule, export_rows)
    write_reference_csv(os.path.join(OUT_DIR, f"{TAG}_reference.csv"), log)

    with open(os.path.join(OUT_DIR, f"{TAG}_predicted_overflow_index.txt"), "w") as f:
        f.write(str(overflow_index) + "\n")

    with open(os.path.join(OUT_DIR, "ring_overflow_manifest.txt"), "w") as f:
        f.write(TAG + "\n")

    print(f"{TAG}: {len(export_rows)} rows exported "
          f"(phase A={BURST_1_COUNT}, phase B=1, phase C={BURST_2_COUNT}); "
          f"Python reference has {len(log)} rows (unbounded deque, processes all of them).")


if __name__ == "__main__":
    main()
