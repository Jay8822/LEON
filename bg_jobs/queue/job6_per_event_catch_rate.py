# bg_jobs/queue/job6_per_event_catch_rate.py
# Added 2026-11-05 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Queue job 6 ("JAY -- APPROVED: per-event catch rate, backward
time, watcher fix", item A). GRACIE watches the whole ship, so a
labelled event spread over many channels should count as caught if
it's flagged on at least one of them -- the existing scorecards only
ever counted channel-label PAIRS, which is why Mission1's 247
Anomaly rows looked like 247 separate events when they're really 34
(RESULTS.md, "Job 2" section).

Covers EVERY monitored channel in both missions, including the
original 16 (Jay: "Redo the original 16 channels' 40 labels as
distinct events too, so the old and new numbers compare like for
like") -- not just the 89 job2 added. STRICT and LOOSE only, one pass
each: catch detection does not depend on the context-check window
(confirmed in RESULTS.md's "v2 rerun" section -- "Anomaly catch rate
is completely unchanged by this"), so there is nothing a second or
third window-pass would add here. trigger_times_sorted=[] throughout
for the same reason (context only ever demotes FALSE alarms from
flagged to logged -- never affects a real catch), which also makes
every new channel's zero context-correlation data (RESULTS.md) a
non-issue for this job specifically.

NO design changes to agents/gracie.py, core/bus.py, or
score_channel_variant's existing behaviour -- return_events=False
stays the default for every existing caller (job2, the original
runs). Reuses score_channel_variant/per_event_hits/derive_rules
directly (run_esa_adb_test_v2.py), same linked_channels derivation
job2 uses (stand_in's jitter_together, filtered to the original 16 --
irrelevant here since leash never fires in any pass, any channel,
either setting, but replicated anyway so this run is a true match to
the real one, not a simplification).

SELF-CHECKING: for every channel+setting already scored in the real
ESA-Mission{1,2}-v2[-allchannels].json, cross-checks this job's own
per-event totals against that file's existing per-channel scorecard
(same total/level-flagged/any-logged numbers, recombined) -- any
mismatch is recorded, not silently dropped, since this job's whole
point is numbers Jay will read and trust.

Checkpointed per channel+setting (resumable). Expensive -- a full
GracieAgent pass per channel+setting, same cost class as job2;
roughly 1/3 of job2's own per-channel time (2 settings here, not the
6 settings x windows job2 ran), so ballpark 22h total across all 105
channels. Meant to run unattended, same as every other queue job.

Run from the repo root:
    python -m bg_jobs.queue.job6_per_event_catch_rate
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
JOB_OUT_PATH = os.path.join(JOB_OUT_DIR, "job6_per_event_catch_rate.json")

MISSIONS = [("ESA-Mission1.zip", "ESA-Mission1"), ("ESA-Mission2.zip", "ESA-Mission2")]
LINKED_CHANNELS_WINDOW = "1min"  # arbitrary -- see module docstring, leash never fires regardless


def _cross_check(channel, setting_name, cause_events, test_labels_with_id, real_checkpoint_path):
    """Compares a ROW-level recount (not per_event's deduplicated-by-
    ID one) against the real checkpoint's existing per-channel
    scorecard for this channel+setting (any window -- catches don't
    vary by window). Returns None if the real checkpoint has nothing
    for this channel yet, else a dict with "ok": bool.

    Must recount at row granularity, not read off per_event: per_event
    is deduplicated by event ID on purpose (that's the whole point of
    the per-event catch rate), so when the same ID has more than one
    row on this one channel -- real, not rare: channel_14's id_189 is
    3 rows for 1 ID; channel_27's id_11 is 2 rows, independently
    caught -- per_event's own "logged"/"flagged" bools collapse those
    rows into one answer, while the real checkpoint counted each row
    on its own. Comparing per_event's numbers directly against the
    real checkpoint looked right on the first few channels (channel_
    14/22/26's extra rows happened to agree on catch status) and only
    broke on channel_27, where they didn't -- caught by not trusting
    that early agreement, not by assuming it would hold."""
    if not os.path.exists(real_checkpoint_path):
        return None
    with open(real_checkpoint_path) as f:
        real = json.load(f)
    channel_entry = real.get(channel)
    if not channel_entry or setting_name not in channel_entry:
        return None
    # Any window -- scorecard totals/catches don't vary by window.
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
        original_16 = set(select_channels(channels_rows))  # same scored_set job2/the original run use

        real_checkpoint_candidates = [
            os.path.join(RESULTS_DIR, f"{prefix}-v2.json"),              # original 16
            os.path.join(RESULTS_DIR, f"{prefix}-v2-allchannels.json"),  # job2's new channels
        ]

        print(f"=== {mission_zip}: {len(monitored)} monitored channels ===")

        for channel in monitored:
            tag_base = f"{prefix}_{channel}"
            # Load once per channel, score both settings, then free --
            # same discipline as job2 (one channel's series in memory
            # at a time; 6GB RAM machine).
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
                        for real_path in real_checkpoint_candidates:
                            check = _cross_check(channel, setting_name, result["_events"], test_labels_with_id, real_path)
                            if check is not None:
                                entry["cross_check"] = check
                                if not check["ok"]:
                                    any_mismatch = True
                                    print(f"!!! CROSS-CHECK MISMATCH {tag} vs {real_path}: {check['mismatches']}")
                                break
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
