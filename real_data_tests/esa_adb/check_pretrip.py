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

MEMORY FIX (2026-10-26, after the first real run crashed): the
original design loaded every one of Mission1's 58 monitored channels
fully into memory at once, up front, and held them all for the whole
run. channel_43 alone is 15.4 million rows -- ~1.7GB as the plain
Python lists load_channel_series returns -- and this machine has 6GB
of RAM total, so that design was never going to fit; it crashed with
MemoryError partway through (confirmed via bg_jobs/pretrip.log), not
from anything to do with the session. Fixed by streaming one other
channel at a time (iter_monitored_channel_rules) instead of
preloading all of them, so peak memory is roughly one target channel
plus one other channel at a time, not 58 at once.

Run from the repo root, after download_esa_adb.py:

    python -m real_data_tests.esa_adb.check_pretrip
"""

import bisect
import gc
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


def iter_monitored_channel_rules(mission_zip, prefix, anomaly_types, cutoff, exclude=()):
    """Yields (channel, secs, values, level_high, level_low, jump_limit)
    for every OTHER monitored channel, ONE AT A TIME -- see the module
    docstring's "MEMORY FIX" note for why this can no longer preload
    all of them into one dict. `secs` (seconds-since-epoch) is still
    precomputed once per channel, not per query -- it's
    channel_moved_in_window() below that's called thousands of times,
    not this."""
    path = os.path.join(DATA_DIR, mission_zip)
    channels_rows = load_channels_csv(path, prefix)
    monitored = [r["Channel"] for r in channels_rows if r["Target"] == "YES" and r["Channel"] not in exclude]
    for ch in monitored:
        try:
            ts, vs = load_channel_series(path, prefix, ch)
            labels = load_labels_for_channel(path, prefix, anomaly_types, ch)
            rules = derive_rules(ts, vs, labels, cutoff)[SETTING_NAME]
            if rules["level_high"] is None or rules["jump_limit"] is None:
                continue
            secs = [t.timestamp() for t in ts]
            del ts
            yield ch, secs, vs, rules["level_high"], rules["level_low"], rules["jump_limit"]
        except Exception as exc:
            print(f"  (skipping {ch} for cross-channel check: {exc!r})")


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


def analyze_channel(channel, mission_zip, prefix, anomaly_types, telecommand_times, rule_values, timestamps, values, labels, cutoff):
    false_transitions, day_starts = false_fault_transitions(channel, rule_values, timestamps, values, labels, cutoff)

    pending = []  # (ts_seconds, rec) -- other_channels_moved filled in below, streamed
    for t in false_transitions:
        ts = t.timestamp()
        day_start = day_starts.get(t.date())
        rec = {
            "timestamp": str(t),
            "time_of_day": t.strftime("%H:%M:%S"),
            "seconds_since_daily_clear": (ts - day_start.timestamp()) if day_start else None,
            "by_window": {w: {"telecommands_fired": [], "other_channels_moved": []} for w in REACTION_WINDOWS_SECONDS},
        }
        for window_name, window_seconds in REACTION_WINDOWS_SECONDS.items():
            lo_ts = ts - window_seconds
            fired = [tc for tc, times in telecommand_times.items()
                     if bisect.bisect_right(times, ts) > bisect.bisect_right(times, lo_ts)]
            rec["by_window"][window_name]["telecommands_fired"] = fired
        pending.append((ts, rec))

    # One other monitored channel in memory at a time -- see
    # iter_monitored_channel_rules's docstring / module "MEMORY FIX" note.
    for other_ch, csecs, cvs, hi, low, jl in iter_monitored_channel_rules(
            mission_zip, prefix, anomaly_types, cutoff, exclude=(channel,)):
        for ts_val, rec in pending:
            for window_name, window_seconds in REACTION_WINDOWS_SECONDS.items():
                lo_ts = ts_val - window_seconds
                if channel_moved_in_window(csecs, cvs, hi, low, jl, lo_ts, ts_val):
                    rec["by_window"][window_name]["other_channels_moved"].append(other_ch)
        del csecs, cvs
        gc.collect()

    records = [rec for _, rec in pending]

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
        results[channel] = analyze_channel(channel, MISSION_ZIP, prefix, anomaly_types,
                                             telecommand_times, rule_values,
                                             timestamps, values, labels, cutoff)
        del timestamps, values
        gc.collect()
        results[channel]["elapsed_seconds"] = time.time() - t0
        with open(out_path, "w") as f:
            json.dump(results, f, default=str, indent=2)
        print(f"{channel}: {results[channel]['n_false_trips']} false trips, "
              f"done in {results[channel]['elapsed_seconds']:.1f}s -- checkpointed.")

    print(f"Written to {out_path}")


if __name__ == "__main__":
    main()
