# bg_jobs/queue/job7_esa_adb_all_channels_clockrule.py
# Added 2026-11-06 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Queue job 7 ("JAY -- SMALL BUILD NOW, THEN ALL RERUNS IN THE
BACKGROUND", item 3a). Full rerun of the ESA-ADB v2 method on EVERY
monitored channel in both missions (105 total: the original 16 plus
job2's 89), now that GRACIE checks clock health first (commit
e6053f7) -- job2/the original run's results all predate that fix
(RESULTS.md, ASSUMPTIONS.md A84) and are LEFT UNTOUCHED, as the
record of what GRACIE did before clock health existed.

NO design changes here, and no changes to run_esa_adb_test(_v2).py --
same functions reused directly, same as job2's own docstring promises.
The only difference from job2_esa_adb_all_channels.py: that job
deliberately EXCLUDES the original 16 (remaining_channels() subtracts
select_channels()'s set) because those 16 already had their own
results; this job scores all 105 together into ONE new, separate file,
since every channel needs re-scoring under the new rule and none of
the old per-channel files are touched or resumed from.

already_scored_set, used only for linked_channels (jitter) filtering,
is every monitored channel in this mission -- by the end of this run
every one of them has real results, same intent as job2's own
"a link only counts if the other channel's data is actually scored"
rule, just over the full 105 instead of the original 16.

Results go to results/ESA-Mission{1,2}-v2-allchannels-clockrule.json
-- NEW filenames, never overwriting ESA-Mission{1,2}-v2.json or
-v2-allchannels.json (Jay: "Never overwrite the old results; they
stay as the record").

Checkpointed per PASS (same granularity/resume semantics as job2).
Expensive: comparable to job2's own multi-day run (job2 covered 89
channels across 6 settings/windows; this covers all 105 the same way)
-- meant to run unattended for days, same as job2.

Run from the repo root:
    python -m bg_jobs.queue.job7_esa_adb_all_channels_clockrule
"""
import gc
import json
import os
import threading
import time

import numpy as np

from real_data_tests.esa_adb.run_esa_adb_test import (
    DATA_DIR, RESULTS_DIR, MISSION_SPANS, CUTOFF_FRACTION,
    load_channel_series, load_channels_csv, load_labels_for_channel, load_anomaly_types,
    derive_rules,
)
from real_data_tests.esa_adb.correlation import REACTION_WINDOWS_SECONDS
from real_data_tests.esa_adb.run_esa_adb_test_v2 import (
    median_sample_interval, score_channel_variant, linked_trigger_times,
    EPISODE_GAP_MULTIPLE, current_working_set_bytes, _log_memory_periodically,
)

JOB_RESULTS_SUFFIX = "-v2-allchannels-clockrule.json"


def _channel_complete(channel_result):
    """Same check as job2_esa_adb_all_channels.py -- duplicated rather
    than imported from it, so this job has no runtime dependency on
    job2's own file (sibling jobs, not a chain; matches how job1/job2/
    job4/job5/job6 are each independent of one another)."""
    from real_data_tests.esa_adb.run_esa_adb_test import SETTINGS
    if channel_result is None or "error" in channel_result:
        return False
    return all(
        setting_name in channel_result
        and all(window_name in channel_result[setting_name] for window_name in REACTION_WINDOWS_SECONDS)
        for setting_name in SETTINGS
    )


def _atomic_write_results(results, results_path):
    tmp_path = results_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(results, f, default=str, indent=2)
    os.replace(tmp_path, results_path)


def all_monitored_channels(mission_zip, prefix):
    path = os.path.join(DATA_DIR, mission_zip)
    channels_rows = load_channels_csv(path, prefix)
    return [r["Channel"] for r in channels_rows if r["Target"] == "YES"]


def run_mission_all(mission_zip, channel_limit_rows=None):
    """channel_limit_rows: ONLY for fast tiny-slice testing, never for
    the real queue run (the real run calls this with None) -- same
    convention as job2_esa_adb_all_channels.run_mission_remaining."""
    prefix = mission_zip.replace(".zip", "")
    path = os.path.join(DATA_DIR, mission_zip)
    results_path = os.path.join(RESULTS_DIR, f"{prefix}{JOB_RESULTS_SUFFIX}")

    results = {}
    if os.path.exists(results_path):
        with open(results_path) as f:
            results = json.load(f)

    channels_rows = load_channels_csv(path, prefix)
    anomaly_types = load_anomaly_types(path, prefix)
    to_do = all_monitored_channels(mission_zip, prefix)
    already_scored_set = set(to_do)  # every monitored channel gets real results in this run
    start, end = MISSION_SPANS[mission_zip]
    cutoff = start + (end - start) * CUTOFF_FRACTION

    with open(os.path.join(RESULTS_DIR, f"{prefix}-stand-in.json")) as f:
        stand_in = json.load(f)
    with open(os.path.join(RESULTS_DIR, f"{prefix}-context.json")) as f:
        context_result = json.load(f)

    print(f"=== {mission_zip}: {len(to_do)} monitored channels (all, clock-health rerun) ===")

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
                    )
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
    print("ESA-ADB v2, ALL 105 monitored channels, clock-health rerun -- queue job 7.")
    stop_memlog = threading.Event()
    memlog_thread = threading.Thread(target=_log_memory_periodically, args=(stop_memlog,), daemon=True)
    memlog_thread.start()
    try:
        for mission in ["ESA-Mission1.zip", "ESA-Mission2.zip"]:
            run_mission_all(mission)
    finally:
        stop_memlog.set()


if __name__ == "__main__":
    main()
