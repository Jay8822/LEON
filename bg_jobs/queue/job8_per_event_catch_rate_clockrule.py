# bg_jobs/queue/job8_per_event_catch_rate_clockrule.py
# Added 2026-11-06 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Queue job 8 ("JAY -- SMALL BUILD NOW, THEN ALL RERUNS IN THE
BACKGROUND", item 3b). Same per-event ("whole ship") catch-rate
recombination as job6_per_event_catch_rate.py, rerun against job7's
clock-health results (results/ESA-Mission{1,2}-v2-allchannels-
clockrule.json) instead of the pre-clock-health files job6 checked
against. Depends on job7 having produced those files -- the compute
queue runs jobs in a fixed order (run_compute_queue.py's JOBS list),
so this must be placed after job7 there.

NO design changes -- reuses score_channel_variant/per_event_hits/
severities_in_window directly, same as job6. linked_channels filtering
stays scoped to the original 16 (select_channels()'s own set), exactly
matching job6's own choice: this never changes catch numbers anyway
(leash fires in no pass, any channel, either setting -- see job6's
docstring), kept only so this run is a true match to job6's method,
not a simplification.

Cross-checks against job7's own per-channel scorecards (not job2's/
the original run's -- those are the pre-clock-health files, the wrong
thing to check a clock-health rerun against).

Results go to bg_jobs/queue/out/job8_per_event_catch_rate_clockrule.
json -- a new file; job6's own output is untouched.

Checkpointed per channel+setting (resumable), same cost class as job6
(~22h across all 105 channels, two settings each).

Run from the repo root:
    python -m bg_jobs.queue.job8_per_event_catch_rate_clockrule
"""
import gc
import json
import os
import time

import numpy as np

from real_data_tests.esa_adb.run_esa_adb_test import (
    DATA_DIR, RESULTS_DIR, MISSION_SPANS, CUTOFF_FRACTION, SETTINGS,
    load_channel_series, load_channels_csv, load_labels_for_channel,
    load_labels_with_id_for_channel, load_anomaly_types, derive_rules, select_channels,
)
from real_data_tests.esa_adb.run_esa_adb_test_v2 import score_channel_variant, per_event_hits, severities_in_window

JOB_OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
JOB_OUT_PATH = os.path.join(JOB_OUT_DIR, "job8_per_event_catch_rate_clockrule.json")

MISSIONS = [("ESA-Mission1.zip", "ESA-Mission1"), ("ESA-Mission2.zip", "ESA-Mission2")]
LINKED_CHANNELS_WINDOW = "1min"  # arbitrary -- see module docstring, leash never fires regardless


def _cross_check(channel, setting_name, cause_events, test_labels_with_id, real_checkpoint_path):
    """Identical recount logic to job6_per_event_catch_rate._cross_check
    (row-granularity, not per_event's deduplicated-by-ID one -- see
    that function's own docstring for why), pointed at job7's clock-
    health results instead of the pre-clock-health files."""
    if not os.path.exists(real_checkpoint_path):
        return None
    with open(real_checkpoint_path) as f:
        real = json.load(f)
    channel_entry = real.get(channel)
    if not channel_entry or setting_name not in channel_entry:
        return None
    windows = channel_entry[setting_name]
    first_window = next(iter(windows.values()), None)
    if first_window is None or "scorecard" not in first_window.get("per_reading", {}):
        return None
    real_scorecard = first_window["per_reading"]["scorecard"]

    recombined = {}
    for _, cat, start, end in test_labels_with_id:
        bucket = recombined.setdefault(cat, {"total_rows": 0, "level_flagged": 0, "any_logged": 0})
        bucket["total_rows"] += 1
        level_hits = severities_in_window(cause_events["level"], start, end)
        if "FAULT" in level_hits:
            bucket["level_flagged"] += 1
        if severities_in_window(cause_events["any"], start, end):
            bucket["any_logged"] += 1

    mismatches = []
    for cat, real_bucket in real_scorecard.items():
        got = recombined.get(cat, {"total_rows": 0, "level_flagged": 0, "any_logged": 0})
        real_total = real_bucket["total"]
        real_level_flagged = real_bucket["level"]["caught_flagged"]
        real_any_logged = real_bucket["any"]["caught_logged"]
        if (got["total_rows"], got["level_flagged"], got["any_logged"]) != (real_total, real_level_flagged, real_any_logged):
            mismatches.append({
                "category": cat, "got": got,
                "real": {"total": real_total, "level_flagged": real_level_flagged, "any_logged": real_any_logged},
            })
    return {"ok": not mismatches, "mismatches": mismatches}


def _atomic_write(results):
    tmp = JOB_OUT_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(results, f, default=str, indent=2)
    os.replace(tmp, JOB_OUT_PATH)


def main():
    os.makedirs(JOB_OUT_DIR, exist_ok=True)
    results = {}
    if os.path.exists(JOB_OUT_PATH):
        with open(JOB_OUT_PATH) as f:
            results = json.load(f)
        print(f"resuming -- {len(results)} channel/setting pair(s) already done")

    any_mismatch = False

    for mission_zip, prefix in MISSIONS:
        path = os.path.join(DATA_DIR, mission_zip)
        channels_rows = load_channels_csv(path, prefix)
        monitored = sorted((r["Channel"] for r in channels_rows if r["Target"] == "YES"),
                            key=lambda c: int(c.rsplit("_", 1)[1]))
        anomaly_types = load_anomaly_types(path, prefix)
        start, end = MISSION_SPANS[mission_zip]
        cutoff = start + (end - start) * CUTOFF_FRACTION

        with open(os.path.join(RESULTS_DIR, f"{prefix}-stand-in.json")) as f:
            stand_in = json.load(f)
        original_16 = set(select_channels(channels_rows))  # same scored_set job6 uses -- see module docstring

        real_checkpoint_path = os.path.join(RESULTS_DIR, f"{prefix}-v2-allchannels-clockrule.json")  # job7's output

        print(f"=== {mission_zip}: {len(monitored)} monitored channels ===")

        for channel in monitored:
            tag_base = f"{prefix}_{channel}"
            need_load = any(f"{tag_base}_{s}" not in results for s in SETTINGS)
            if not need_load:
                continue
            t0 = time.time()
            timestamps, values = load_channel_series(path, prefix, channel)
            values = np.asarray(values, dtype=np.float64)
            labels = load_labels_for_channel(path, prefix, anomaly_types, channel)
            labels_with_id = load_labels_with_id_for_channel(path, prefix, anomaly_types, channel)
            test_labels_with_id = [(i, c, s, e) for i, c, s, e in labels_with_id
                                    if e >= cutoff and c != "Communication Gap"]
            rules = derive_rules(timestamps, values, labels, cutoff)
            jitter = stand_in["jitter_together"].get(LINKED_CHANNELS_WINDOW, {}).get(channel, [])
            noise_band = stand_in["noise_bands"].get(channel, {})

            for setting_name, rule_values in rules.items():
                tag = f"{tag_base}_{setting_name}"
                if tag in results:
                    continue
                try:
                    linked_channels = [d["linked_to"] for d in jitter if d["linked_to"] in original_16]
                    result = score_channel_variant(
                        channel, rule_values, linked_channels, timestamps, values, labels, cutoff,
                        noise_band, 60, [], None,
                        log_nominal_readings=False, log_publishes=False, return_events=True,
                    )
                    if "skipped" in result:
                        results[tag] = {"skipped": result["skipped"]}
                    else:
                        per_event = per_event_hits(result["_events"], test_labels_with_id)
                        entry = {"per_event": per_event, "elapsed_seconds": time.time() - t0}
                        check = _cross_check(channel, setting_name, result["_events"], test_labels_with_id, real_checkpoint_path)
                        if check is not None:
                            entry["cross_check"] = check
                            if not check["ok"]:
                                any_mismatch = True
                                print(f"!!! CROSS-CHECK MISMATCH {tag} vs {real_checkpoint_path}: {check['mismatches']}")
                        results[tag] = entry
                    _atomic_write(results)
                    print(f"{tag}: done -- checkpointed.")
                except Exception as exc:
                    results[tag] = {"error": repr(exc)}
                    _atomic_write(results)
                    print(f"{tag}: FAILED -- {exc!r}")

            timestamps = values = labels = labels_with_id = None
            gc.collect()

    n_ok = sum(1 for r in results.values() if "error" not in r and "skipped" not in r)
    print(f"\n{n_ok}/{len(results)} channel/setting pairs scored. "
          f"Cross-check mismatches found: {any_mismatch}. Written to {JOB_OUT_PATH}")


if __name__ == "__main__":
    main()
