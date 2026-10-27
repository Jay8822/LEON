# real_data_tests/esa_adb/check_masking.py
# Added 2026-10-26 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Step 2b of the "Ccode update.txt" four-step round: is the masking
hypothesis (ASSUMPTIONS.md A76) real? For each Mission1 Anomaly event
that STRICT's level sense missed, checks whether that channel was
ALREADY latched FAULT the moment the anomaly's window opened -- and,
if so, when that latch began and whether the crossing that caused it
was itself inside a different labelled window (a real catch of
something else) or genuinely unlabelled (a false alarm).

LOOK ONLY -- reuses run_esa_adb_test.py's exact derivation and replay
method unchanged (same rules, same daily clear_fault(reset_leash_
timer=False), same GRACE_SECONDS), just with extra bookkeeping around
each Anomaly event. Does not change scoring or any result already
committed.

Mission1, STRICT only -- that's the setting and mission the masking
hypothesis was raised against (RESULTS.md's "Honest findings").

Run from the repo root, after download_esa_adb.py:

    python -m real_data_tests.esa_adb.check_masking
"""

import json
import os
import time
from datetime import timedelta

from agents.gracie import GracieAgent
from agents.gracie_rulebook import ChannelRule
from core.bus import EventBus

from real_data_tests.esa_adb.run_esa_adb_test import (
    DATA_DIR,
    RESULTS_DIR,
    MISSION_SPANS,
    CUTOFF_FRACTION,
    GRACE_SECONDS,
    LEASH_WINDOW_SECONDS,
    LEASH_SOFT_DURATION_SECONDS,
    LEASH_HARD_DURATION_SECONDS,
    load_channel_series,
    load_channels_csv,
    load_labels_for_channel,
    load_anomaly_types,
    label_at,
    select_channels,
    derive_rules,
)

MISSION_ZIP = "ESA-Mission1.zip"
SETTING_NAME = "STRICT"


def check_channel(channel, rule_values, timestamps, values, labels, cutoff):
    if any(rule_values[k] is None for k in
           ("level_high", "level_low", "jump_limit", "leash_slope_limit")):
        return {"skipped": "insufficient nominal training days to derive a limit"}

    rule = ChannelRule(
        name=channel, units="u",
        level_high=rule_values["level_high"], level_low=rule_values["level_low"],
        jump_limit=rule_values["jump_limit"],
        leash_window_seconds=LEASH_WINDOW_SECONDS,
        leash_slope_limit=rule_values["leash_slope_limit"],
        leash_soft_duration_seconds=LEASH_SOFT_DURATION_SECONDS,
        leash_hard_duration_seconds=LEASH_HARD_DURATION_SECONDS,
        stuck_window_seconds=LEASH_WINDOW_SECONDS, min_normal_noise=0.0,  # Stillness not exercised here
    )
    bus = EventBus()
    gracie = GracieAgent(bus, {channel: rule})

    test_events = sorted(
        [(s, e) for cat, s, e in labels if cat == "Anomaly" and e >= cutoff],
        key=lambda se: se[0],
    )
    pending = list(enumerate(test_events))  # (idx, (start, end)), not yet snapshotted
    snapshot = {}  # event index -> (pre_event_latch, latch_began_at)
    fault_windows = []  # (t_start, t_end) of every continuous FAULT latch this run

    prior_latched = "NOMINAL"
    latch_began_at = None
    last_day = None

    for t, v in zip(timestamps, values):
        if t < cutoff:
            continue
        if label_at(t, labels) == "Communication Gap":
            continue

        day = t.date()
        if last_day is not None and day != last_day:
            gracie.clear_fault(reset_leash_timer=False)
        last_day = day

        # Snapshot the latch state for any event whose window has just opened,
        # BEFORE processing this sample (so the snapshot reflects "already
        # latched", not any effect of this very reading).
        while pending and t >= pending[0][1][0] - timedelta(seconds=GRACE_SECONDS):
            idx, _ = pending.pop(0)
            snapshot[idx] = (prior_latched, latch_began_at)

        gracie.process_readings({channel: v}, timestamp=t.timestamp())
        new_latched = gracie._last_readings[channel]["severity"]

        if new_latched == "FAULT" and prior_latched != "FAULT":
            latch_began_at = t
        elif new_latched != "FAULT":
            if prior_latched == "FAULT" and latch_began_at is not None:
                fault_windows.append((latch_began_at, t))
            latch_began_at = None
        prior_latched = new_latched

    if prior_latched == "FAULT" and latch_began_at is not None:
        fault_windows.append((latch_began_at, timestamps[-1] if timestamps else None))

    def caught(start, end):
        # Matches run_esa_adb_test.py's score_test_period() exactly: a
        # catch is the TRANSITION MOMENT into FAULT landing inside the
        # grace window, not the latch merely still being held FAULT
        # from an earlier, unrelated crossing. An interval-overlap
        # check would misclassify an already-latched channel's old
        # fault as "catching" the new anomaly underneath it -- exactly
        # the masking question this script exists to answer, so it
        # must not be blurred here.
        lo, hi = start.timestamp() - GRACE_SECONDS, end.timestamp() + GRACE_SECONDS
        return any(lo <= fs.timestamp() <= hi for fs, _fe in fault_windows)

    missed = []
    for idx, (start, end) in enumerate(test_events):
        if caught(start, end):
            continue
        pre_latch, began_at = snapshot.get(idx, ("NOMINAL", None))
        entry = {
            "event_start": str(start), "event_end": str(end),
            "already_latched_fault": pre_latch == "FAULT",
        }
        if pre_latch == "FAULT" and began_at is not None:
            origin_label = label_at(began_at, labels)
            entry["latch_began_at"] = str(began_at)
            entry["latch_origin_label"] = origin_label  # None = false alarm (unlabelled)
        missed.append(entry)

    return {
        "n_anomaly_events": len(test_events),
        "n_missed": len(missed),
        "n_missed_already_latched_false": sum(
            1 for m in missed if m["already_latched_fault"] and m.get("latch_origin_label") is None
        ),
        "missed": missed,
    }


def main():
    print("ESA-ADB masking check (Step 2b, A76) -- LOOK ONLY. Mission1, STRICT.")
    path = os.path.join(DATA_DIR, MISSION_ZIP)
    prefix = MISSION_ZIP.replace(".zip", "")
    channels_rows = load_channels_csv(path, prefix)
    anomaly_types = load_anomaly_types(path, prefix)
    selected = select_channels(channels_rows)
    start, end = MISSION_SPANS[MISSION_ZIP]
    cutoff = start + (end - start) * CUTOFF_FRACTION
    print(f"Selected channels (same fixed seed as the scored run): {selected}")

    results_path = os.path.join(RESULTS_DIR, "masking-check.json")
    results = {}
    if os.path.exists(results_path):
        with open(results_path) as f:
            results = json.load(f)

    for channel in selected:
        if channel in results:
            print(f"{channel}: already done, skipping (resume).")
            continue
        t0 = time.time()
        try:
            timestamps, values = load_channel_series(path, prefix, channel)
            labels = load_labels_for_channel(path, prefix, anomaly_types, channel)
            rules = derive_rules(timestamps, values, labels, cutoff)
            rule_values = rules[SETTING_NAME]
            results[channel] = check_channel(channel, rule_values, timestamps, values, labels, cutoff)
            results[channel]["elapsed_seconds"] = time.time() - t0
        except Exception as exc:
            results[channel] = {"error": repr(exc), "elapsed_seconds": time.time() - t0}
            print(f"{channel}: FAILED after {results[channel]['elapsed_seconds']:.1f}s -- {exc!r}")

        os.makedirs(RESULTS_DIR, exist_ok=True)
        with open(results_path, "w") as f:
            json.dump(results, f, default=str, indent=2)
        if "error" not in results[channel]:
            print(f"{channel}: done in {results[channel]['elapsed_seconds']:.1f}s -- "
                  f"{results[channel].get('n_missed', 0)}/{results[channel].get('n_anomaly_events', 0)} missed -- checkpointed.")

    print(f"Written to {results_path}")


if __name__ == "__main__":
    main()
