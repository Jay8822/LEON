# real_data_tests/esa_adb/check_pretrip.py
# Added 2026-10-26 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Step 1 of the follow-up round: "check the basics first" -- what
happens just before each of channel_43/channel_45's FALSE FAULT trips
(Mission1, STRICT)? For every FAULT transition that lands outside
every labelled window:
- which telecommands fired in the preceding 1 minute, 10 minutes, 1
  hour (same three windows as the correlation work).
- which OTHER monitored channels jumped (sample-to-sample rate over
  THEIR OWN STRICT jump_limit) or crossed (value over THEIR OWN
  STRICT level bounds) in the same three windows.
- time of day, and how long since the daily clear_fault().

LOOK ONLY -- no scoring change, no verdict. A "false trip" here means
exactly what RESULTS.md's false_counts already means: a FAULT
transition whose timestamp falls outside every labelled window
(Communication Gap already excluded upstream). Reuses the same replay
method as run_esa_adb_test.py / check_masking.py (same rules, same
daily clear_fault(reset_leash_timer=False)).

Run from the repo root, after download_esa_adb.py:

    python -m real_data_tests.esa_adb.check_pretrip
"""

import bisect
import json
import os
import time
from collections import Counter
from datetime import timedelta

from agents.gracie import GracieAgent
from agents.gracie_rulebook import ChannelRule
from core.bus import EventBus

from real_data_tests.esa_adb.run_esa_adb_test import (
    DATA_DIR,
    RESULTS_DIR,
    MISSION_SPANS,
    CUTOFF_FRACTION,
    LEASH_WINDOW_SECONDS,
    LEASH_SOFT_DURATION_SECONDS,
    LEASH_HARD_DURATION_SECONDS,
    load_channel_series,
    load_channels_csv,
    load_labels_for_channel,
    load_anomaly_types,
    label_at,
    derive_rules,
)
from real_data_tests.esa_adb.learn_context import load_telecommand_ids, load_telecommand_times
from real_data_tests.esa_adb.correlation import REACTION_WINDOWS_SECONDS

MISSION_ZIP = "ESA-Mission1.zip"
SETTING_NAME = "STRICT"
TARGET_CHANNELS = ["channel_43", "channel_45"]


def false_fault_transitions(channel, rule_values, timestamps, values, labels, cutoff):
    """Replays through the real GracieAgent, same method as the real
    scoring, and returns every FAULT-transition timestamp that is NOT
    inside any labelled window -- one entry per episode, not per
    sample."""
    rule = ChannelRule(
        name=channel, units="u",
        level_high=rule_values["level_high"], level_low=rule_values["level_low"],
        jump_limit=rule_values["jump_limit"],
        leash_window_seconds=LEASH_WINDOW_SECONDS,
        leash_slope_limit=rule_values["leash_slope_limit"],
        leash_soft_duration_seconds=LEASH_SOFT_DURATION_SECONDS,
        leash_hard_duration_seconds=LEASH_HARD_DURATION_SECONDS,
    )
    bus = EventBus()
    gracie = GracieAgent(bus, {channel: rule})
    test_labels = [(cat, s, e) for cat, s, e in labels if e >= cutoff and cat != "Communication Gap"]

    transitions, day_starts = [], {}
    prior_latched, last_day = "NOMINAL", None
    for t, v in zip(timestamps, values):
        if t < cutoff:
            continue
        if label_at(t, labels) == "Communication Gap":
            continue
        day = t.date()
        if last_day is not None and day != last_day:
            gracie.clear_fault(reset_leash_timer=False)
        if day not in day_starts:
            day_starts[day] = t
        last_day = day

        gracie.process_readings({channel: v}, timestamp=t.timestamp())
        new_latched = gracie._last_readings[channel]["severity"]
        if new_latched == "FAULT" and prior_latched != "FAULT":
            transitions.append(t)
        prior_latched = new_latched

    return [t for t in transitions if label_at(t, test_labels) is None], day_starts


def load_all_monitored(mission_zip, prefix, anomaly_types, cutoff, exclude=()):
    """{channel: (secs, values, level_high, level_low, jump_limit)} for
    every OTHER monitored channel -- STRICT thresholds, derived the
    normal way. `secs` (seconds-since-epoch) is precomputed ONCE here,
    not per query -- channel_moved_in_window() below is called
    thousands of times, so re-deriving .timestamp() per call would be
    the dominant cost by far."""
    path = os.path.join(DATA_DIR, mission_zip)
    channels_rows = load_channels_csv(path, prefix)
    monitored = [r["Channel"] for r in channels_rows if r["Target"] == "YES" and r["Channel"] not in exclude]
    out = {}
    for ch in monitored:
        try:
            ts, vs = load_channel_series(path, prefix, ch)
            labels = load_labels_for_channel(path, prefix, anomaly_types, ch)
            rules = derive_rules(ts, vs, labels, cutoff)[SETTING_NAME]
            if rules["level_high"] is None or rules["jump_limit"] is None:
                continue
            secs = [t.timestamp() for t in ts]
            out[ch] = (secs, vs, rules["level_high"], rules["level_low"], rules["jump_limit"])
        except Exception as exc:
            print(f"  (skipping {ch} for cross-channel check: {exc!r})")
    return out


def channel_moved_in_window(secs, vs, level_high, level_low, jump_limit, window_start_ts, window_end_ts):
    """True if this channel crossed its own STRICT level bounds, or
    jumped past its own STRICT jump_limit, anywhere in
    (window_start_ts, window_end_ts]. `secs` is precomputed."""
    lo = bisect.bisect_right(secs, window_start_ts)
    hi = bisect.bisect_right(secs, window_end_ts)
    if hi <= lo:
        return False
    for i in range(lo, hi):
        if vs[i] > level_high or vs[i] < level_low:
            return True
        if i > 0:
            dt = secs[i] - secs[i - 1]
            if dt > 0 and abs(vs[i] - vs[i - 1]) / dt > jump_limit:
                return True
    return False


def analyze_channel(channel, other_channels, telecommand_times, rule_values, timestamps, values, labels, cutoff):
    false_transitions, day_starts = false_fault_transitions(channel, rule_values, timestamps, values, labels, cutoff)

    records = []
    for t in false_transitions:
        ts = t.timestamp()
        day_start = day_starts.get(t.date())
        rec = {
            "timestamp": str(t),
            "time_of_day": t.strftime("%H:%M:%S"),
            "seconds_since_daily_clear": (ts - day_start.timestamp()) if day_start else None,
            "by_window": {},
        }
        for window_name, window_seconds in REACTION_WINDOWS_SECONDS.items():
            lo_ts = ts - window_seconds
            fired = [tc for tc, times in telecommand_times.items()
                     if bisect.bisect_right(times, ts) > bisect.bisect_right(times, lo_ts)]
            moved = [ch for ch, (csecs, cvs, hi, low, jl) in other_channels.items()
                     if channel_moved_in_window(csecs, cvs, hi, low, jl, lo_ts, ts)]
            rec["by_window"][window_name] = {"telecommands_fired": fired, "other_channels_moved": moved}
        records.append(rec)

    # Summaries: most common telecommands/channels across all false trips, per window.
    summary = {}
    for window_name in REACTION_WINDOWS_SECONDS:
        tc_counts = Counter(tc for r in records for tc in r["by_window"][window_name]["telecommands_fired"])
        ch_counts = Counter(ch for r in records for ch in r["by_window"][window_name]["other_channels_moved"])
        n_with_any_tc = sum(1 for r in records if r["by_window"][window_name]["telecommands_fired"])
        n_with_any_ch = sum(1 for r in records if r["by_window"][window_name]["other_channels_moved"])
        summary[window_name] = {
            "n_false_trips_with_a_telecommand": n_with_any_tc,
            "n_false_trips_with_another_channel_moving": n_with_any_ch,
            "top_telecommands": tc_counts.most_common(10),
            "top_other_channels": ch_counts.most_common(10),
        }

    tod_seconds = [t.hour * 3600 + t.minute * 60 + t.second for t in false_transitions]
    since_clear = [r["seconds_since_daily_clear"] for r in records if r["seconds_since_daily_clear"] is not None]

    return {
        "n_false_trips": len(false_transitions),
        "summary_by_window": summary,
        "time_of_day_seconds": tod_seconds,
        "seconds_since_daily_clear": since_clear,
        "records": records,
    }


def main():
    print("ESA-ADB pre-trip check (Step 1, new round) -- LOOK ONLY. Mission1, STRICT, channel_43/channel_45.")
    prefix = MISSION_ZIP.replace(".zip", "")
    path = os.path.join(DATA_DIR, MISSION_ZIP)
    anomaly_types = load_anomaly_types(path, prefix)
    start, end = MISSION_SPANS[MISSION_ZIP]
    cutoff = start + (end - start) * CUTOFF_FRACTION

    print("Loading all monitored channels' STRICT thresholds once (shared across both target channels)...")
    other_channels_full = load_all_monitored(MISSION_ZIP, prefix, anomaly_types, cutoff)
    print(f"Loaded {len(other_channels_full)} monitored channels for cross-channel checks.")

    tc_ids = load_telecommand_ids(path, prefix)
    telecommand_times = {tc: sorted(load_telecommand_times(path, prefix, tc)) for tc in tc_ids}
    print(f"Loaded {len(telecommand_times)} telecommand firing series.")

    out_path = os.path.join(RESULTS_DIR, "pretrip-check.json")
    os.makedirs(RESULTS_DIR, exist_ok=True)
    results = {}
    if os.path.exists(out_path):
        with open(out_path) as f:
            results = json.load(f)

    for channel in TARGET_CHANNELS:
        if channel in results:
            print(f"{channel}: already done, skipping (resume).")
            continue
        t0 = time.time()
        timestamps, values = load_channel_series(path, prefix, channel)
        labels = load_labels_for_channel(path, prefix, anomaly_types, channel)
        rule_values = derive_rules(timestamps, values, labels, cutoff)[SETTING_NAME]
        others = {ch: v for ch, v in other_channels_full.items() if ch != channel}
        results[channel] = analyze_channel(channel, others, telecommand_times, rule_values,
                                            timestamps, values, labels, cutoff)
        results[channel]["elapsed_seconds"] = time.time() - t0
        with open(out_path, "w") as f:
            json.dump(results, f, default=str, indent=2)
        print(f"{channel}: {results[channel]['n_false_trips']} false trips, "
              f"done in {results[channel]['elapsed_seconds']:.1f}s -- checkpointed.")

    print(f"Written to {out_path}")


if __name__ == "__main__":
    main()
