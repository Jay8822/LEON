# bg_jobs/queue/job2_esa_adb_all_channels.py
# Added 2026-10-28 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Queue job 2 of 5 ("keep the laptop working while usage is low" --
Ccode update.txt). Runs the EXISTING, frozen v2 ESA-ADB method
(real_data_tests/esa_adb/run_esa_adb_test_v2.py -- its scoring
functions reused directly, not reimplemented) on every monitored
channel NOT already in the original 16 (8 per mission, from
select_channels()) -- Mission1 has 58 monitored (50 new), Mission2
has 47 (39 new), confirmed via load_channels_csv()/select_channels()
earlier this session.

NO design changes. Same STRICT/LOOSE derivation, same per-reading AND
per-episode counts, same noise-filter instrumentation, same numpy-
array memory fix. The ORIGINAL 16 channels' result files
(results/ESA-Mission{1,2}-v2.json) are never opened for writing by
this script -- new channels go to results/ESA-Mission{1,2}-v2-
allchannels.json, a separate file.

HONEST LIMITATION, not a bug, not fixed here (reusing EXISTING
results only, per instruction -- extending it would be new work, a
separate decision): learn_context.py's training-only command/event
correlation was explicitly scoped to the original 16 channels only
(see its own module docstring). Every new channel here has NO entry
in that context_result, so linked_trigger_times() returns an empty
list for them -- context-tagging has zero effect on any new channel's
score, identical to running without it. stand_in_blueprint.py's noise
bands, by contrast, WERE computed for every monitored channel, so
those are real for every new channel too.

Checkpointed per PASS (one of 6 settings/windows combinations per
channel), not just per channel -- changed 2026-11-04 (speed-up round)
after stopping the live run for the logging/label_at fixes cost a
full redo of the channel then in progress, since the old per-channel-
only checkpoint had nothing to resume from mid-channel. Resume never
re-enters GRACIE mid-pass; it only ever skips passes already on disk
and starts the next whole one, same as a first run. This will take a
long time -- expected, meant to run unattended for days.

Run from the repo root:
    python -m bg_jobs.queue.job2_esa_adb_all_channels
"""
import gc
import json
import os
import threading
import time

import numpy as np

from real_data_tests.esa_adb.run_esa_adb_test import (
    DATA_DIR, RESULTS_DIR, MISSION_SPANS, CUTOFF_FRACTION, SETTINGS,
    load_channel_series, load_channels_csv, load_labels_for_channel, load_anomaly_types,
    select_channels, derive_rules,
)
from real_data_tests.esa_adb.correlation import REACTION_WINDOWS_SECONDS
from real_data_tests.esa_adb.run_esa_adb_test_v2 import (
    median_sample_interval, score_channel_variant, linked_trigger_times,
    EPISODE_GAP_MULTIPLE, current_working_set_bytes, _log_memory_periodically,
)

JOB_RESULTS_SUFFIX = "-v2-allchannels.json"


def _channel_complete(channel_result):
    """True only if every setting x window pass is present and there's
    no recorded error. SETTINGS/REACTION_WINDOWS_SECONDS are both
    fixed, known dicts -- this never needs to load the channel's data."""
    if channel_result is None or "error" in channel_result:
        return False
    return all(
        setting_name in channel_result
        and all(window_name in channel_result[setting_name] for window_name in REACTION_WINDOWS_SECONDS)
        for setting_name in SETTINGS
    )


def _atomic_write_results(results, results_path):
    # Atomic (write-then-replace): the 2026-10-29 disk-full crash hit
    # this exact pattern in run_compute_queue.py's own status file and
    # left it truncated/unreadable -- this checkpoint is the one thing
    # that must survive that, since it's what resume reads back.
    tmp_path = results_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(results, f, default=str, indent=2)
    os.replace(tmp_path, results_path)


def remaining_channels(mission_zip, prefix):
    path = os.path.join(DATA_DIR, mission_zip)
    channels_rows = load_channels_csv(path, prefix)
    monitored = [r["Channel"] for r in channels_rows if r["Target"] == "YES"]
    already_scored = set(select_channels(channels_rows))
    return [ch for ch in monitored if ch not in already_scored], already_scored


def run_mission_remaining(mission_zip, channel_limit_rows=None):
    """channel_limit_rows: if set, truncates each channel's series to
    this many samples -- ONLY for fast tiny-slice testing, never for
    the real queue run (the real run calls this with None)."""
    prefix = mission_zip.replace(".zip", "")
    path = os.path.join(DATA_DIR, mission_zip)
    results_path = os.path.join(RESULTS_DIR, f"{prefix}{JOB_RESULTS_SUFFIX}")

    results = {}
    if os.path.exists(results_path):
        with open(results_path) as f:
            results = json.load(f)

    channels_rows = load_channels_csv(path, prefix)
    anomaly_types = load_anomaly_types(path, prefix)
    to_do, already_scored_set = remaining_channels(mission_zip, prefix)
    # scored_set for linked_channels filtering: the ORIGINAL 16's own
    # scored_set, matching run_esa_adb_test_v2.py's own semantics --
    # a new channel's jitter links (if any) only count if they point
    # at an already-scored channel, same rule as before.
    start, end = MISSION_SPANS[mission_zip]
    cutoff = start + (end - start) * CUTOFF_FRACTION

    with open(os.path.join(RESULTS_DIR, f"{prefix}-stand-in.json")) as f:
        stand_in = json.load(f)
    with open(os.path.join(RESULTS_DIR, f"{prefix}-context.json")) as f:
        context_result = json.load(f)

    print(f"=== {mission_zip}: {len(to_do)} new channels (not in the original 16) ===")

    for channel in to_do:
        if _channel_complete(results.get(channel)):
            print(f"{channel}: already done, skipping (resume).")
            continue
        t0 = time.time()
        try:
            timestamps, values = load_channel_series(path, prefix, channel)
            if channel_limit_rows is not None:
                timestamps, values = timestamps[:channel_limit_rows], values[:channel_limit_rows]
            values = np.asarray(values, dtype=np.float64)
            labels = load_labels_for_channel(path, prefix, anomaly_types, channel)
            rules = derive_rules(timestamps, values, labels, cutoff)
            episode_gap_seconds = None
            interval = median_sample_interval(timestamps)
            if interval is not None:
                episode_gap_seconds = EPISODE_GAP_MULTIPLE * interval
            noise_band = stand_in["noise_bands"].get(channel, {})

            # Resume at PASS granularity (2026-11-04, speed-up round):
            # a channel used to only ever get written to disk after ALL
            # 6 passes finished, so any interruption mid-channel lost
            # everything done on it so far -- this is what made the
            # speed-up fix cost a full redo of channel_18. Never
            # resumes GRACIE mid-pass -- each pass is its own fresh
            # GracieAgent/EventBus regardless, so "resume" only ever
            # means "start the next whole pass," same as a first run.
            existing = results.get(channel)
            channel_result = dict(existing) if existing is not None else {}
            channel_result.pop("error", None)
            channel_result["n_samples"] = len(values)
            channel_result["episode_gap_seconds"] = episode_gap_seconds

            for setting_name, rule_values in rules.items():
                channel_result.setdefault(setting_name, {})
                for window_name, window_seconds in REACTION_WINDOWS_SECONDS.items():
                    if window_name in channel_result[setting_name]:
                        continue  # this pass already checkpointed -- resume, don't redo
                    jitter = stand_in["jitter_together"].get(window_name, {}).get(channel, [])
                    linked_channels = [d["linked_to"] for d in jitter if d["linked_to"] in already_scored_set]
                    trigger_times = linked_trigger_times(
                        path, prefix, mission_zip, channel, setting_name, window_name, context_result
                    )  # empty for every new channel -- see module docstring
                    channel_result[setting_name][window_name] = score_channel_variant(
                        channel, rule_values, linked_channels, timestamps, values, labels, cutoff,
                        noise_band, window_seconds, trigger_times, episode_gap_seconds,
                        log_nominal_readings=False, log_publishes=False,
                    )
                    results[channel] = channel_result
                    _atomic_write_results(results, results_path)
                    print(f"{channel}/{setting_name}/{window_name}: done -- checkpointed.")

            channel_result["elapsed_seconds"] = time.time() - t0
            results[channel] = channel_result
            _atomic_write_results(results, results_path)
            print(f"{channel}: done in {channel_result['elapsed_seconds']:.1f}s -- checkpointed.")
        except Exception as exc:
            elapsed = time.time() - t0
            channel_result = results.get(channel, {})
            channel_result["error"] = repr(exc)
            channel_result["elapsed_seconds"] = elapsed
            results[channel] = channel_result
            _atomic_write_results(results, results_path)
            print(f"{channel}: FAILED after {elapsed:.1f}s -- {exc!r}")

        timestamps = values = labels = None
        gc.collect()

    return results


def main():
    print("ESA-ADB v2, all remaining monitored channels -- queue job 2.")
    stop_memlog = threading.Event()
    memlog_thread = threading.Thread(target=_log_memory_periodically, args=(stop_memlog,), daemon=True)
    memlog_thread.start()
    try:
        for mission in ["ESA-Mission1.zip", "ESA-Mission2.zip"]:
            run_mission_remaining(mission)
    finally:
        stop_memlog.set()


if __name__ == "__main__":
    main()
