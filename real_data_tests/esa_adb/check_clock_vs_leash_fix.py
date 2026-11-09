# real_data_tests/esa_adb/check_clock_vs_leash_fix.py
# Added 2026-11-09 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Proves the clock/leash misclassification fix (run_esa_adb_test_v2.py,
"2026-11-09 fix" in that file's own docstring) on a small FRESH sample,
without rerunning job7/8 (Ccode update.txt, "JAY -- MONDAY", item 1).

Jay's hypothesis, from an independent chat's read of job7/8: the new
"leash" false flags that appeared after the clock-health rerun are
really clock faults, misfiled by the old level_hit_now guess -- the
per-channel counts matched the DST jump counts exactly. This script
checks all three claims directly, on 3 channels per mission (picked
from job7's real results for showing the "mostly 4 per channel" (M1)
/ "mostly 1 per channel" (M2) pattern Jay described):

  1. leash = 0 once correctly separated from clock.
  2. clock count == the OLD "leash" count already recorded for that
     exact channel/setting/window in job7's real results (read-only --
     job7's files are never written to).
  3. every clock-flagged event's own timestamp falls on a DST jump
     date (the EU's "last Sunday of March", per ASSUMPTIONS.md A84) --
     not just "some date in spring", the EXACT predicted date.

STRICT/1min only -- catch detection and false-count attribution don't
vary by window (RESULTS.md's own "v2 rerun" finding), so one window is
enough to prove the classification fix; it's not what's in question.

Run from the repo root, after download_esa_adb.py and after job7 has
produced its real results (read, never written, by this script):

    python -m real_data_tests.esa_adb.check_clock_vs_leash_fix
"""
import datetime
import json
import os

from real_data_tests.esa_adb.run_esa_adb_test import (
    DATA_DIR, RESULTS_DIR, MISSION_SPANS, CUTOFF_FRACTION,
    load_channel_series, load_labels_for_channel, load_anomaly_types, derive_rules,
)
from real_data_tests.esa_adb.run_esa_adb_test_v2 import score_channel_variant, linked_trigger_times

SAMPLE_CHANNELS = {
    "ESA-Mission1.zip": ["channel_12", "channel_13", "channel_17"],
    "ESA-Mission2.zip": ["channel_9", "channel_10", "channel_11"],
}
SETTING_NAME = "STRICT"
WINDOW_NAME = "1min"
WINDOW_SECONDS = 60


def last_sunday_of_march(year):
    d = datetime.date(year, 3, 31)
    while d.weekday() != 6:  # Monday=0 ... Sunday=6
        d -= datetime.timedelta(days=1)
    return d


def check_channel(mission_zip, prefix, channel, anomaly_types, cutoff, stand_in, context_result,
                   real_checkpoint):
    path = os.path.join(DATA_DIR, mission_zip)
    timestamps, values = load_channel_series(path, prefix, channel)
    labels = load_labels_for_channel(path, prefix, anomaly_types, channel)
    rules = derive_rules(timestamps, values, labels, cutoff)
    rule_values = rules[SETTING_NAME]

    jitter = stand_in["jitter_together"].get(WINDOW_NAME, {}).get(channel, [])
    linked_channels = [d["linked_to"] for d in jitter]  # harmless either way -- leash never fires regardless
    trigger_times = linked_trigger_times(path, prefix, mission_zip, channel, SETTING_NAME, WINDOW_NAME, context_result)
    noise_band = stand_in["noise_bands"].get(channel, {})

    result = score_channel_variant(
        channel, rule_values, linked_channels, timestamps, values, labels, cutoff,
        noise_band, WINDOW_SECONDS, trigger_times, None,
        log_nominal_readings=False, log_publishes=False, return_events=True,
    )
    cause_events = result["_events"]
    n_leash = len(cause_events["leash"])
    n_clock = len(cause_events["clock"])

    real_entry = real_checkpoint.get(channel, {}).get(SETTING_NAME, {}).get(WINDOW_NAME, {})
    old_n_leash = real_entry.get("per_reading", {}).get("n_leash_events")

    dst_dates = {last_sunday_of_march(y) for y in range(timestamps[0].year, timestamps[-1].year + 1)}
    clock_dates = [t.date() for t, _ in cause_events["clock"]]
    off_dst = [d for d in clock_dates if d not in dst_dates]

    return {
        "channel": channel,
        "n_leash_new": n_leash,
        "n_clock_new": n_clock,
        "old_n_leash_from_job7": old_n_leash,
        "clock_matches_old_leash": n_clock == old_n_leash,
        "clock_dates": sorted(str(d) for d in set(clock_dates)),
        "clock_events_off_dst_date": [str(d) for d in off_dst],
        "all_clock_events_on_dst_date": len(off_dst) == 0,
    }


def main():
    print("Clock/leash misclassification fix -- sample proof (STRICT/1min, 3 channels per mission).")
    all_ok = True
    results = {}
    for mission_zip, channels in SAMPLE_CHANNELS.items():
        prefix = mission_zip.replace(".zip", "")
        path = os.path.join(DATA_DIR, mission_zip)
        anomaly_types = load_anomaly_types(path, prefix)
        start, end = MISSION_SPANS[mission_zip]
        cutoff = start + (end - start) * CUTOFF_FRACTION

        with open(os.path.join(RESULTS_DIR, f"{prefix}-stand-in.json")) as f:
            stand_in = json.load(f)
        with open(os.path.join(RESULTS_DIR, f"{prefix}-context.json")) as f:
            context_result = json.load(f)
        with open(os.path.join(RESULTS_DIR, f"{prefix}-v2-allchannels-clockrule.json")) as f:
            real_checkpoint = json.load(f)  # job7's real output -- read only, never written

        results[mission_zip] = {}
        for channel in channels:
            r = check_channel(mission_zip, prefix, channel, anomaly_types, cutoff, stand_in,
                               context_result, real_checkpoint)
            results[mission_zip][channel] = r
            ok = r["n_leash_new"] == 0 and r["clock_matches_old_leash"] and r["all_clock_events_on_dst_date"]
            all_ok = all_ok and ok
            print(f"  {mission_zip}/{channel}: leash={r['n_leash_new']} clock={r['n_clock_new']} "
                  f"(old 'leash' was {r['old_n_leash_from_job7']}) "
                  f"dates={r['clock_dates']} all-on-DST={r['all_clock_events_on_dst_date']} "
                  f"-- {'PASS' if ok else 'MISMATCH'}")

    print(f"\n{'ALL PASS' if all_ok else 'MISMATCH FOUND'}: leash=0, clock count matches the old "
          f"'leash' count exactly, every clock event lands on a predicted DST date -- "
          f"{'confirms' if all_ok else 'does NOT confirm'} the misclassification hypothesis.")

    out_path = os.path.join(RESULTS_DIR, "clock-vs-leash-fix-check.json")
    with open(out_path, "w") as f:
        json.dump(results, f, default=str, indent=2)
    print(f"Written to {out_path}")


if __name__ == "__main__":
    main()
