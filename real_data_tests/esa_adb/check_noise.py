# real_data_tests/esa_adb/check_noise.py
# Added 2026-10-26 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Step 2a of the "Ccode update.txt" four-step round: did channel_43
and channel_45 get NOISIER in the test period, rather than drift?
LOOK ONLY -- no GracieAgent, no scoring, no verdicts.

Compares training vs. test periods on PEAKS and SPREAD, not the
average: daily maximum and minimum, high/low percentiles (95th/5th and
99th/1st, matching the STRICT/LOOSE derivation percentiles already
used elsewhere), and day-to-day spread of those daily peaks (IQR of
the daily maxima, IQR of the daily minima). Same exclusions as
measure_drift.py and derive_rules(): labelled rows (Anomaly, Rare
Event) and Communication Gap are dropped before looking at "normal"
behaviour, so a real anomaly's own spike doesn't get counted as noise.

Run from the repo root, after download_esa_adb.py:

    python -m real_data_tests.esa_adb.check_noise
"""

import json
import os

from real_data_tests.opssat_ad.run_opssat_ad_test import percentile
from real_data_tests.esa_adb.run_esa_adb_test import (
    DATA_DIR,
    MISSION_SPANS,
    CUTOFF_FRACTION,
    load_channel_series,
    load_labels_for_channel,
    load_anomaly_types,
    label_at,
)

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

CHANNELS = {
    "ESA-Mission1.zip": ["channel_43", "channel_45"],
}


def iqr(values):
    if not values:
        return None
    return percentile(values, 75) - percentile(values, 25)


def check_channel(mission_zip, prefix, channel, anomaly_types, cutoff):
    timestamps, values = load_channel_series(os.path.join(DATA_DIR, mission_zip), prefix, channel)
    labels = load_labels_for_channel(os.path.join(DATA_DIR, mission_zip), prefix, anomaly_types, channel)

    by_day = {}
    for t, v in zip(timestamps, values):
        category = label_at(t, labels)
        if category is not None:
            continue  # excluded -- labelled (Anomaly/Rare Event/Communication Gap), not normal behaviour
        by_day.setdefault(t.date(), []).append(v)

    def period_stats(predicate):
        daily_max, daily_min, all_values = [], [], []
        for day, vals in by_day.items():
            if not predicate(day):
                continue
            daily_max.append(max(vals))
            daily_min.append(min(vals))
            all_values.extend(vals)
        if not all_values:
            return None
        return {
            "n_days": len(daily_max),
            "n_readings": len(all_values),
            "median": percentile(all_values, 50),
            "p95": percentile(all_values, 95),
            "p5": percentile(all_values, 5),
            "p99": percentile(all_values, 99),
            "p1": percentile(all_values, 1),
            "daily_max_median": percentile(daily_max, 50) if daily_max else None,
            "daily_min_median": percentile(daily_min, 50) if daily_min else None,
            "daily_max_iqr": iqr(daily_max),
            "daily_min_iqr": iqr(daily_min),
        }

    train = period_stats(lambda day: day < cutoff.date())
    test = period_stats(lambda day: day >= cutoff.date())
    return {"train": train, "test": test}


def main():
    print("ESA-ADB noise check (Step 2a) -- LOOK ONLY. No GracieAgent, no scoring.")
    results = {}
    for mission_zip, channels in CHANNELS.items():
        prefix = mission_zip.replace(".zip", "")
        path = os.path.join(DATA_DIR, mission_zip)
        anomaly_types = load_anomaly_types(path, prefix)
        start, end = MISSION_SPANS[mission_zip]
        cutoff = start + (end - start) * CUTOFF_FRACTION
        results[mission_zip] = {}
        for channel in channels:
            print(f"--- {mission_zip} / {channel} ---")
            r = check_channel(mission_zip, prefix, channel, anomaly_types, cutoff)
            results[mission_zip][channel] = r
            for period_name in ("train", "test"):
                s = r[period_name]
                print(f"  {period_name}: n_days={s['n_days']} median={s['median']:.4g} "
                      f"p95={s['p95']:.4g} p5={s['p5']:.4g} p99={s['p99']:.4g} p1={s['p1']:.4g} "
                      f"daily_max_median={s['daily_max_median']:.4g} daily_max_iqr={s['daily_max_iqr']:.4g} "
                      f"daily_min_median={s['daily_min_median']:.4g} daily_min_iqr={s['daily_min_iqr']:.4g}")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "noise-check.json")
    with open(out_path, "w") as f:
        json.dump(results, f, default=str, indent=2)
    print(f"Written to {out_path}")


if __name__ == "__main__":
    main()
