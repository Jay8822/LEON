# real_data_tests/esa_adb/measure_drift.py
# Added 2026-10-25 — Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Measures real long-term drift across every monitored ESA-ADB
channel, both missions. LOOK, DON'T SCORE: no GracieAgent, no
scorecards, no verdicts -- pure descriptive statistics on the real
channel data, which is why this covers all 105 monitored channels
(58 Mission1 + 47 Mission2), not just the 16 already scored in
run_esa_adb_test.py -- far cheaper than driving a real agent sample
by sample.

Design, agreed with Jay before building:

- Labelled rows (Anomaly, Rare Event) are excluded before measuring
  "normal behaviour" drift, same principle as training derivation --
  one long Rare Event could otherwise distort a whole year's median.
  Communication Gap rows are dropped entirely, same as the scored
  test.
- Spread is IQR (25th-75th percentile), not standard deviation --
  robust to whatever labelled spikes slip through.
- "Overall slope" is a single linear regression of each year's median
  against the year index -- one units-per-year number per channel.
  Not claiming this captures anything nonlinear, just a first, honest
  summary.
- "Step changes" are a simple heuristic, not a real change-point
  algorithm: flag a step wherever consecutive years' medians differ
  by more than 2x that channel's own overall IQR. Labelled plainly as
  a heuristic throughout.
- Test-period distance: the test period's own median, expressed as a
  number of TRAINING-period IQRs away from the training period's own
  median -- same shared per-mission cutoff date as the scored test,
  directly answering "is this why the false-fault count was so high"
  from RESULTS.md.

Run from the repo root, after download_esa_adb.py:

    python -m real_data_tests.esa_adb.measure_drift
"""

import csv
import io
import json
import os
import time
import zipfile

from real_data_tests.opssat_ad.run_opssat_ad_test import percentile
from real_data_tests.esa_adb.run_esa_adb_test import (
    DATA_DIR,
    MISSION_SPANS,
    CUTOFF_FRACTION,
    load_channel_series,
    load_channels_csv,
    load_labels_for_channel,
    load_anomaly_types,
    label_at,
)

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
STEP_HEURISTIC_MULTIPLE = 2.0  # a year-to-year median jump > this many IQRs counts as a "step"


def ols_slope(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return None
    return num / den


def iqr(values):
    if not values:
        return None
    return percentile(values, 75) - percentile(values, 25)


def measure_channel(mission_zip, prefix, channel, anomaly_types, cutoff):
    timestamps, values = load_channel_series(mission_zip, prefix, channel)
    labels = load_labels_for_channel(mission_zip, prefix, anomaly_types, channel)

    nominal_by_year = {}
    train_nominal, test_nominal = [], []
    for t, v in zip(timestamps, values):
        if label_at(t, labels) is not None:
            continue  # excluded -- labelled, not nominal
        nominal_by_year.setdefault(t.year, []).append(v)
        if t < cutoff:
            train_nominal.append(v)
        else:
            test_nominal.append(v)

    years = sorted(nominal_by_year)
    year_medians = [percentile(nominal_by_year[y], 50) for y in years]
    overall_values = [v for y in years for v in nominal_by_year[y]]
    overall_iqr = iqr(overall_values)

    steps = []
    for i in range(1, len(year_medians)):
        if overall_iqr and abs(year_medians[i] - year_medians[i - 1]) > STEP_HEURISTIC_MULTIPLE * overall_iqr:
            steps.append({"from_year": years[i - 1], "to_year": years[i],
                          "median_change": year_medians[i] - year_medians[i - 1]})

    slope = ols_slope(years, year_medians) if len(years) >= 2 else None

    train_median, train_iqr = percentile(train_nominal, 50) if train_nominal else None, iqr(train_nominal)
    test_median = percentile(test_nominal, 50) if test_nominal else None
    test_distance_iqrs = None
    if train_median is not None and test_median is not None and train_iqr:
        test_distance_iqrs = (test_median - train_median) / train_iqr

    return {
        "n_years": len(years),
        "years": years,
        "year_medians": year_medians,
        "overall_iqr": overall_iqr,
        "slope_units_per_year": slope,
        "step_changes": steps,
        "train_median": train_median,
        "train_iqr": train_iqr,
        "test_median": test_median,
        "test_distance_training_iqrs": test_distance_iqrs,
    }


def run_mission(mission_zip_filename):
    path = os.path.join(DATA_DIR, mission_zip_filename)
    prefix = mission_zip_filename.replace(".zip", "")
    results_path = os.path.join(RESULTS_DIR, f"{prefix}-drift.json")

    results = {}
    if os.path.exists(results_path):
        with open(results_path) as f:
            results = json.load(f)

    channels_rows = load_channels_csv(path, prefix)
    anomaly_types = load_anomaly_types(path, prefix)
    monitored = [r["Channel"] for r in channels_rows if r["Target"] == "YES"]
    start, end = MISSION_SPANS[mission_zip_filename]
    cutoff = start + (end - start) * CUTOFF_FRACTION

    print(f"=== {mission_zip_filename}: {len(monitored)} monitored channels ===")
    for channel in monitored:
        if channel in results:
            continue
        t0 = time.time()
        try:
            results[channel] = measure_channel(path, prefix, channel, anomaly_types, cutoff)
        except Exception as exc:
            results[channel] = {"error": repr(exc)}
        results[channel]["elapsed_seconds"] = time.time() - t0

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(results_path, "w") as f:
        json.dump(results, f, default=str, indent=2)
    print(f"{mission_zip_filename}: done, {len(results)} channels, written to {results_path}")
    return results


def main():
    print("ESA-ADB long-term drift measurement -- LOOK, DON'T SCORE. No GracieAgent, no verdicts.")
    for mission in ["ESA-Mission1.zip", "ESA-Mission2.zip"]:
        run_mission(mission)


if __name__ == "__main__":
    main()
