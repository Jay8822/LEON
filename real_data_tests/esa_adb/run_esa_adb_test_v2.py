# real_data_tests/esa_adb/run_esa_adb_test_v2.py
# Added 2026-10-26 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Third ESA-ADB pass -- the 26 October 2026 four-step round's rerun.
Layers on top of run_esa_adb_test.py's follow-up run (same 16
channels, same cutoffs, same STRICT/LOOSE settings, same daily
clear_fault(reset_leash_timer=False)):

(a) The learned stand-in's `linked_channels` (stand_in_blueprint.py) --
    wired into each ChannelRule exactly like any other rule-book value.
    HONEST NOTE: this has NO effect on scoring in this dataset.
    linked_channels only matters for leash's settling exception
    (_is_part_of_active_major_fault), and leash has never fired once in
    ESA-ADB across every prior pass. Built and wired correctly anyway,
    reported as a null result, not skipped.
(b) Noise-filter instrumentation (SPEC.md's new Blueprint section) --
    for each test-period sample, classifies the sample-to-sample delta
    as "explained" (within the stand-in's noise band) or not, and
    counts both. Does NOT alter anything fed to GracieAgent -- this
    round builds it as a measurement, not a live filter wired into
    jump detection. Reason, found while building this: jump_limit is
    already a 95th/99th-percentile EXTREME of day-level rate, so it
    already excludes ordinary noise by construction; the enormous
    jump count flagged in RESULTS.md's follow-up section came from
    sustained elevated-but-still-above-jump_limit days, not borderline
    noise, so filtering "normal noise" out of jump detection wouldn't
    have touched that finding. Reported as a measurement alongside the
    real scorecard, not silently expanded into an unapproved scoring
    change.
(c) Context-checking (learn_context.py) -- GRACIE's new
    `expected_causes` input (agents/gracie.py, module docstring point
    12), fed from training-only command/event correlation. Run and
    reported for all three reaction windows separately (1 minute, 10
    minutes, 1 hour) -- never just the nicer-looking one.
(d) Per-reading AND per-episode counts, side by side, for every cause
    (level/jump/leash/any) and every false-alarm count. An episode is
    a run of same-cause events with no gap longer than 3x that
    channel's own median sample interval (Jay's fixed, labelled test
    choice) -- computed once per channel, not a global constant, since
    channels are sampled at very different rates.

MEMORY (2026-10-27, after LEON_v2_rerun died overnight with no
traceback -- see Ccode update.txt): `values` is now converted to a
numpy float64 array right after loading, instead of staying the plain
Python list load_channel_series returns -- a list of boxed Python
floats costs roughly 4x a numpy float64 array for the same data, and
a single channel can be 15M+ rows on this 6GB machine. `timestamps`
deliberately stays a plain list of datetime objects: derive_rules(),
label_at() and this module's own loop all call .date()/.timestamp()
on each one, which numpy's datetime64 doesn't support without a
larger rewrite -- left alone to keep this change provably safe rather
than guessing at a bigger one. Proved equivalent against the already-
checkpointed (pre-conversion) result for channel_78
(scratchpad/prove_numpy_equivalence.py, 2026-10-27) before trusting
it. Also added a once-a-minute working-set memory log (Windows-only,
via psapi, no new dependency) so a future crash leaves a trail.

Prerequisites (run first, their results are read here):
    python -m real_data_tests.esa_adb.stand_in_blueprint
    python -m real_data_tests.esa_adb.learn_context

Run from the repo root:
    python -m real_data_tests.esa_adb.run_esa_adb_test_v2
"""

import bisect
import ctypes
import gc
import json
import os
import statistics
import threading
import time

import numpy as np

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
    SETTINGS,
    load_channel_series,
    load_channels_csv,
    load_labels_for_channel,
    load_anomaly_types,
    label_at,
    select_channels,
    derive_rules,
)
from real_data_tests.esa_adb.correlation import REACTION_WINDOWS_SECONDS
from real_data_tests.esa_adb.learn_context import load_telecommand_times, load_event_times

EPISODE_GAP_MULTIPLE = 3.0  # Jay's Step 4.5: a gap of more than 3x the channel's own median sample interval
MEMLOG_INTERVAL_SECONDS = 60.0


class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


_kernel32 = ctypes.WinDLL("kernel32.dll")
_kernel32.GetCurrentProcess.restype = ctypes.c_void_p
_psapi = ctypes.WinDLL("psapi.dll")
_psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_PROCESS_MEMORY_COUNTERS), ctypes.c_ulong]
_psapi.GetProcessMemoryInfo.restype = ctypes.c_int


def current_working_set_bytes():
    """This process's current working set (RSS), via psapi -- no extra
    dependency (psutil isn't installed), Windows-only like this whole
    machine's job-running setup. GetCurrentProcess() returns a
    pseudo-handle (-1, i.e. all bits set on 64-bit) -- without the
    explicit restype/argtypes above, ctypes mis-marshals that and
    GetProcessMemoryInfo silently fails every time. Caught by actually
    testing this before trusting it, not assumed to work."""
    counters = _PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(_PROCESS_MEMORY_COUNTERS)
    handle = _kernel32.GetCurrentProcess()
    ok = _psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
    return counters.WorkingSetSize if ok else None


def _log_memory_periodically(stop_event):
    """Runs in a daemon thread for the life of the process -- logs once
    a minute, flushed immediately (not left to stdout's normal
    buffering), so a future crash leaves a trail of what memory looked
    like right up to it. See module docstring's "MEMORY" note."""
    while not stop_event.wait(MEMLOG_INTERVAL_SECONDS):
        bytes_used = current_working_set_bytes()
        if bytes_used is not None:
            print(f"[mem] working set: {bytes_used / 1e6:.1f} MB", flush=True)


def median_sample_interval(timestamps):
    if len(timestamps) < 2:
        return None
    diffs = [(timestamps[i] - timestamps[i - 1]).total_seconds() for i in range(1, len(timestamps))]
    return statistics.median(diffs)


def _collapse(events, episode_gap_seconds):
    """events: chronological [(datetime, severity), ...]. Returns one
    entry per episode: (first_timestamp, worst_severity_in_episode) --
    a run of events with no gap longer than episode_gap_seconds counts
    as one episode (Jay's Step 4.5)."""
    if not events or episode_gap_seconds is None:
        return list(events)
    out = []
    cur_start, cur_worst = events[0]
    cur_last = events[0][0]
    for t, sev in events[1:]:
        if (t - cur_last).total_seconds() <= episode_gap_seconds:
            if _rank(sev) > _rank(cur_worst):
                cur_worst = sev
            cur_last = t
        else:
            out.append((cur_start, cur_worst))
            cur_start, cur_worst, cur_last = t, sev, t
    out.append((cur_start, cur_worst))
    return out


_RANK = {"NOMINAL": 0, "WARNING": 1, "FAULT": 2}


def _rank(sev):
    return _RANK.get(sev, 0)


def _score(cause_events, test_labels):
    """Same scorecard/false_counts method as run_esa_adb_test.py's
    score_test_period(), extracted so it can run twice -- once on raw
    per-reading events, once on per-episode-collapsed events."""

    def severities_in_window(events, start, end):
        lo, hi = start.timestamp() - GRACE_SECONDS, end.timestamp() + GRACE_SECONDS
        return [sev for t, sev in events if lo <= t.timestamp() <= hi]

    scorecard = {}
    for category, start, end in test_labels:
        bucket = scorecard.setdefault(category, {
            "total": 0,
            **{cause: {"caught_logged": 0, "caught_flagged": 0} for cause in cause_events}
        })
        bucket["total"] += 1
        for cause, events in cause_events.items():
            hits = severities_in_window(events, start, end)
            if hits:
                bucket[cause]["caught_logged"] += 1
            if "FAULT" in hits:
                bucket[cause]["caught_flagged"] += 1

    false_counts = {cause: {"false_logged": 0, "false_flagged": 0} for cause in cause_events}
    for cause, events in cause_events.items():
        for t, sev in events:
            if label_at(t, test_labels) is not None:
                continue
            false_counts[cause]["false_flagged" if sev == "FAULT" else "false_logged"] += 1

    return scorecard, false_counts


def linked_trigger_times(path, prefix, mission_zip, channel, setting_name, window_name, context_result):
    """Merged, sorted firing times (telecommands + events, full range --
    not training-only) for whatever's linked for this channel/setting/
    window, per learn_context.py's discovery."""
    entry = context_result.get(channel, {}).get(setting_name, {})
    linked = entry.get("linked", {}).get(window_name, {"telecommands": {}, "events": {}})
    times = []
    for tc_id in linked["telecommands"]:
        times.extend(load_telecommand_times(path, prefix, tc_id))
    if linked["events"]:
        all_events = load_event_times(path, prefix)
        for ev_id in linked["events"]:
            times.extend(all_events.get(ev_id, []))
    return sorted(times)


def score_channel_variant(channel, rule_values, linked_channels, timestamps, values, labels, cutoff,
                           noise_band, window_seconds, trigger_times_sorted, episode_gap_seconds):
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
        level_fault_class=None, jump_fault_class=None, leash_soft_fault_class=None,
        leash_hard_fault_class=None, stillness_fault_class=None,  # Item C: not stated this round
        linked_channels=tuple(linked_channels),
    )
    bus = EventBus()
    gracie = GracieAgent(bus, {channel: rule})

    level_events, jump_events, leash_events, any_events = [], [], [], []
    prior_latched, prior_aggregate, last_day, last_value = "NOMINAL", "NOMINAL", None, None
    explained_noise, total_deltas = 0, 0
    big_change_cutoff = noise_band.get("big_change_cutoff") if noise_band else None

    for t, v in zip(timestamps, values):
        if t < cutoff:
            continue
        if label_at(t, labels) == "Communication Gap":
            continue
        day = t.date()
        if last_day is not None and day != last_day:
            gracie.clear_fault(reset_leash_timer=False)
        last_day = day

        if last_value is not None and big_change_cutoff is not None:
            total_deltas += 1
            if abs(v - last_value) <= big_change_cutoff:
                explained_noise += 1
        last_value = v

        level_hit_now = v > rule.level_high or v < rule.level_low

        ts = t.timestamp()
        lo_idx = bisect.bisect_left(trigger_times_sorted, ts - window_seconds)
        hi_idx = bisect.bisect_right(trigger_times_sorted, ts)
        expected = hi_idx > lo_idx

        # {channel: None} -- a cause was (statistically) commanded,
        # but training-only command/event correlation genuinely can't
        # claim to know its expected SIZE (agents/gracie.py module
        # docstring, point 13), so None preserves the original
        # "any value in the window is excused" behaviour exactly.
        gracie.process_readings({channel: v}, timestamp=ts,
                                 expected_causes=({channel: None} if expected else None))

        new_latched = gracie._last_readings[channel]["severity"]
        jump_now = gracie._last_readings[channel]["jump"]
        new_aggregate = gracie.health_state

        if new_latched != prior_latched and new_latched in ("WARNING", "FAULT"):
            (level_events if level_hit_now else leash_events).append((t, new_latched))
        prior_latched = new_latched

        if jump_now:
            jump_events.append((t, "WARNING"))

        if new_aggregate != prior_aggregate and new_aggregate in ("WARNING", "FAULT"):
            any_events.append((t, new_aggregate))
        prior_aggregate = new_aggregate

    test_labels = [(cat, s, e) for cat, s, e in labels if e >= cutoff and cat != "Communication Gap"]
    cause_events = {"level": level_events, "jump": jump_events, "leash": leash_events, "any": any_events}

    per_reading_scorecard, per_reading_false = _score(cause_events, test_labels)
    episode_events = {cause: _collapse(events, episode_gap_seconds) for cause, events in cause_events.items()}
    per_episode_scorecard, per_episode_false = _score(episode_events, test_labels)

    return {
        "rule": rule_values,
        "linked_channels": list(linked_channels),
        "noise_filter": {"explained": explained_noise, "total_deltas": total_deltas,
                          "cutoff": big_change_cutoff},
        "per_reading": {
            "scorecard": per_reading_scorecard, "false_counts": per_reading_false,
            "n_level_events": len(level_events), "n_jump_events": len(jump_events),
            "n_leash_events": len(leash_events),
        },
        "per_episode": {
            "scorecard": per_episode_scorecard, "false_counts": per_episode_false,
            "n_level_events": len(episode_events["level"]), "n_jump_events": len(episode_events["jump"]),
            "n_leash_events": len(episode_events["leash"]),
        },
    }


def run_mission(mission_zip):
    prefix = mission_zip.replace(".zip", "")
    path = os.path.join(DATA_DIR, mission_zip)
    results_path = os.path.join(RESULTS_DIR, f"{prefix}-v2.json")

    results = {}
    if os.path.exists(results_path):
        with open(results_path) as f:
            results = json.load(f)

    channels_rows = load_channels_csv(path, prefix)
    anomaly_types = load_anomaly_types(path, prefix)
    selected = select_channels(channels_rows)
    scored_set = set(selected)
    start, end = MISSION_SPANS[mission_zip]
    cutoff = start + (end - start) * CUTOFF_FRACTION

    with open(os.path.join(RESULTS_DIR, f"{prefix}-stand-in.json")) as f:
        stand_in = json.load(f)
    with open(os.path.join(RESULTS_DIR, f"{prefix}-context.json")) as f:
        context_result = json.load(f)

    print(f"=== {mission_zip} (v2: context-checking x3 windows, stand-in linked_channels, "
          f"noise-filter instrumentation, per-reading + per-episode) ===")
    print(f"Selected channels: {selected}")

    for channel in selected:
        if channel in results:
            print(f"{channel}: already done, skipping (resume).")
            continue
        t0 = time.time()
        try:
            timestamps, values = load_channel_series(path, prefix, channel)
            values = np.asarray(values, dtype=np.float64)  # see module docstring's "MEMORY" note
            labels = load_labels_for_channel(path, prefix, anomaly_types, channel)
            rules = derive_rules(timestamps, values, labels, cutoff)
            episode_gap_seconds = None
            interval = median_sample_interval(timestamps)
            if interval is not None:
                episode_gap_seconds = EPISODE_GAP_MULTIPLE * interval
            noise_band = stand_in["noise_bands"].get(channel, {})

            channel_result = {"n_samples": len(values), "episode_gap_seconds": episode_gap_seconds}
            for setting_name, rule_values in rules.items():
                channel_result[setting_name] = {}
                for window_name, window_seconds in REACTION_WINDOWS_SECONDS.items():
                    jitter = stand_in["jitter_together"].get(window_name, {}).get(channel, [])
                    linked_channels = [d["linked_to"] for d in jitter if d["linked_to"] in scored_set]
                    trigger_times = linked_trigger_times(
                        path, prefix, mission_zip, channel, setting_name, window_name, context_result
                    )
                    channel_result[setting_name][window_name] = score_channel_variant(
                        channel, rule_values, linked_channels, timestamps, values, labels, cutoff,
                        noise_band, window_seconds, trigger_times, episode_gap_seconds,
                    )
            channel_result["elapsed_seconds"] = time.time() - t0
        except Exception as exc:
            channel_result = {"error": repr(exc), "elapsed_seconds": time.time() - t0}
            print(f"{channel}: FAILED after {channel_result['elapsed_seconds']:.1f}s -- {exc!r}")

        results[channel] = channel_result
        with open(results_path, "w") as f:
            json.dump(results, f, default=str, indent=2)
        if "error" not in channel_result:
            print(f"{channel}: done in {channel_result['elapsed_seconds']:.1f}s -- checkpointed.")

        # Precautionary, not a confirmed fix for the 2026-10-27 unexplained
        # crash (no traceback, so the cause wasn't pinned down -- see
        # Ccode update.txt) -- each channel's series is multi-million rows
        # (up to ~1.7GB as plain Python lists), and this machine has 6GB
        # RAM total, so dropping the big local names explicitly before the
        # next iteration's load can't hurt even if reference counting was
        # already doing this on its own.
        timestamps = values = labels = None
        gc.collect()

    return results


def main():
    print("ESA-ADB v2 (Step 3+4 rerun) -- FIRST TEST AGAINST REAL SPACECRAFT DATA. NOT A VALIDATION.")
    stop_memlog = threading.Event()
    memlog_thread = threading.Thread(target=_log_memory_periodically, args=(stop_memlog,), daemon=True)
    memlog_thread.start()
    try:
        for mission in ["ESA-Mission1.zip", "ESA-Mission2.zip"]:
            run_mission(mission)
    finally:
        stop_memlog.set()


if __name__ == "__main__":
    main()
