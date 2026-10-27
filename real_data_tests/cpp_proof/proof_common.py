# real_data_tests/cpp_proof/proof_common.py
# Added 2026-10-27 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Shared plumbing for NEW TASK 1b's cross-language equivalence proof:
exports one channel's readings + its already-derived rule-book values
to plain files a C++ proof executable can read without any parsing
beyond split-on-comma/split-on-equals (Power-of-10-simple), and runs
the REAL agents.gracie.GracieAgent over the identical rows to produce
a reference verdict log in the exact same shape.

This proves the DETECTION/latching logic only -- rule-book values are
exported from Python's already-derived numbers (whichever real-data
test harness derived them), never re-derived in C++.

Faithfulness note: new_crossing_while_latched is derived from a
before/after snapshot of state.level_crossing_active and
state.latched_severity -- not re-implemented logic, just reading the
exact condition agents/gracie.py's _process_level branches on (already
an accepted pattern in this codebase: agents/gracie_test.py reads
gracie._states[channel].level_crossing_active directly). leash_settled
and the slope actually used this cycle are captured by temporarily
wrapping GracieAgent._process_leash, so neither value is re-derived --
they're read straight from the real code's own call.
"""
import csv
import os

import agents.gracie as gracie_module
from agents.gracie import GracieAgent
from agents.gracie_rulebook import ChannelRule
from core.bus import EventBus

PROOF_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(PROOF_DIR, "out")

READINGS_HEADER = ["sample_index", "timestamp", "value", "clear_before"]
VERDICT_HEADER = ["sample_index", "severity", "jump_event", "leash_settled",
                  "new_crossing_while_latched", "has_slope", "slope"]


def write_sidecar(path, rule: ChannelRule):
    with open(path, "w") as f:
        f.write(f"level_high={rule.level_high!r}\n")
        f.write(f"level_low={rule.level_low!r}\n")
        f.write(f"jump_limit={rule.jump_limit!r}\n")
        f.write(f"leash_window_seconds={rule.leash_window_seconds!r}\n")
        f.write(f"leash_slope_limit={rule.leash_slope_limit!r}\n")
        f.write(f"leash_soft_duration_seconds={rule.leash_soft_duration_seconds!r}\n")
        f.write(f"leash_hard_duration_seconds={rule.leash_hard_duration_seconds!r}\n")
        f.write(f"linked_channels={','.join(rule.linked_channels)}\n")


def write_readings_csv(path, rows):
    """rows: [(sample_index, timestamp_seconds, value, clear_before_bool), ...]."""
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(READINGS_HEADER)
        for idx, ts, val, clear_before in rows:
            w.writerow([idx, repr(ts), repr(val), 1 if clear_before else 0])


def write_reference_csv(path, log):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(VERDICT_HEADER)
        for row in log:
            w.writerow([
                row["sample_index"], row["severity"], int(row["jump_event"]),
                int(row["leash_settled"]), int(row["new_crossing_while_latched"]),
                int(row["has_slope"]), repr(row["slope"]),
            ])


def run_reference(channel, rule: ChannelRule, rows):
    """Drives the REAL GracieAgent over `rows` (same shape as
    write_readings_csv's input), calling clear_fault(channel,
    reset_leash_timer=False) immediately before any row flagged
    clear_before -- matching real_data_tests/esa_adb's day-boundary
    driving pattern exactly. Returns a list of dicts in
    VERDICT_HEADER's shape."""
    bus = EventBus()
    gracie = GracieAgent(bus, {channel: rule})
    state = gracie._states[channel]

    captured_leash = []  # (slope_or_None, outcome_or_None), appended once per process_readings call
    original_process_leash = gracie_module.GracieAgent._process_leash

    def wrapped_process_leash(self, ch, st, ts, slope):
        outcome = original_process_leash(self, ch, st, ts, slope)
        captured_leash.append((slope, outcome))
        return outcome

    gracie_module.GracieAgent._process_leash = wrapped_process_leash
    log = []
    try:
        for idx, ts, val, clear_before in rows:
            if clear_before:
                gracie.clear_fault(channel, reset_leash_timer=False)
            prior_severity = state.latched_severity
            prior_level_crossing_active = state.level_crossing_active

            gracie.process_readings({channel: val}, timestamp=ts)

            new_crossing_while_latched = (
                (not prior_level_crossing_active)
                and state.level_crossing_active
                and prior_severity == "FAULT"
            )
            slope, outcome = captured_leash[-1]
            log.append({
                "sample_index": idx,
                "severity": state.latched_severity,
                "jump_event": bool(gracie._last_readings[channel]["jump"]),
                "leash_settled": outcome == "settled",
                "new_crossing_while_latched": new_crossing_while_latched,
                "has_slope": slope is not None,
                "slope": slope if slope is not None else 0.0,
            })
    finally:
        gracie_module.GracieAgent._process_leash = original_process_leash

    return log
