# bg_jobs/queue/job4_battery_ageing.py
# Added 2026-10-28 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Queue job 4 of 5 ("keep the laptop working while usage is low" --
Ccode update.txt). LOOK ONLY -- no GRACIE, no scoring, no threshold.
Measures real battery ageing from
real_data_tests/nasa_liion_battery_aging/data/1. BatteryAgingARC-
FY08Q4.zip (batteries B0005, B0006, B0007, B0018 -- the four Jay
named explicitly), per real_data_tests/nasa_liion_battery_aging/
PROFILE.md's already-confirmed `.mat` structure.

SCOPE, decided here, stated plainly: only zip #1 of the six ARC
archives (batteries 5/6/7/18) -- the other five (batteries 25-56) are
a different, larger set Jay's instruction didn't name; not opened
this round, same "only the first archive inspected" limit the
PROFILE.md already states. The supplementary randomized-usage dataset
(real_data_tests/nasa_randomized_battery/) is SKIPPED this round --
its per-step .mat structure is genuinely different (no direct
per-cycle Capacity field; health has to be inferred from its periodic
reference cycles instead) and doesn't fit this job's time budget
alongside the other four queue jobs; noted here, not silently
dropped.

Measures, per battery, from its DISCHARGE cycles only (the ones with
a real `Capacity` field) in recorded order:
- Capacity fade per cycle (the Capacity sequence itself).
- Fade RATE per cycle (consecutive delta, not just the cumulative
  curve).
- Whether fade accelerates near end-of-life: mean |fade rate| in the
  first 20% of discharge cycles vs. the last 20% (a fixed split,
  decided before computing anything, not picked after looking).
- Voltage/temperature drift over life: each cycle's own mean
  Voltage_measured and peak Temperature_measured, tracked cycle to
  cycle.
- The real EOL point: the first cycle whose Capacity drops to <=70%
  of that battery's own FIRST discharge cycle's capacity (the
  dataset's own documented 30%-fade criterion, confirmed in
  PROFILE.md's quote of the dataset's own README).

Small dataset (616 cycles x 4 batteries, ~16MB each) -- no streaming
needed, no checkpointing needed (whole job completes in well under a
minute, confirmed by the tiny-slice test before this was trusted at
full scale).

Run from the repo root:
    python -m bg_jobs.queue.job4_battery_ageing
"""
import json
import os
import tempfile
import zipfile

import numpy as np
import scipy.io as sio

DATA_ZIP = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..",
    "real_data_tests", "nasa_liion_battery_aging", "data", "1. BatteryAgingARC-FY08Q4.zip",
)
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
OUT_PATH = os.path.join(OUT_DIR, "job4_battery_ageing.json")

BATTERIES = ["B0005", "B0006", "B0007", "B0018"]
EOL_FRACTION = 0.70  # 30% fade -- the dataset's own documented EOL criterion
EARLY_LATE_SPLIT = 0.20  # first/last 20% of discharge cycles, fixed in advance


def load_battery(z, name):
    raw = z.read(f"{name}.mat")
    with tempfile.NamedTemporaryFile(suffix=".mat", delete=False) as tf:
        tf.write(raw)
        tmppath = tf.name
    try:
        d = sio.loadmat(tmppath, simplify_cells=True)
    finally:
        os.unlink(tmppath)
    return d[name]["cycle"]


def analyze_battery(cycles):
    discharge = [c for c in cycles if c["type"] == "discharge"]
    capacities = np.array([c["data"]["Capacity"] for c in discharge], dtype=float)
    mean_voltage = np.array([float(np.mean(c["data"]["Voltage_measured"])) for c in discharge])
    peak_temp = np.array([float(np.max(c["data"]["Temperature_measured"])) for c in discharge])

    fade_rate = np.diff(capacities)  # per-cycle delta, negative = fading
    n = len(capacities)
    split = max(1, int(n * EARLY_LATE_SPLIT))
    early_rate = fade_rate[:split]
    late_rate = fade_rate[-split:]

    initial_capacity = float(capacities[0])
    eol_threshold = initial_capacity * EOL_FRACTION
    eol_cycle_indices = np.nonzero(capacities <= eol_threshold)[0]
    eol_cycle = int(eol_cycle_indices[0]) if len(eol_cycle_indices) else None

    return {
        "n_discharge_cycles": n,
        "initial_capacity": initial_capacity,
        "final_capacity": float(capacities[-1]),
        "total_fade_fraction": float(1.0 - capacities[-1] / initial_capacity),
        "eol_threshold_70pct": eol_threshold,
        "eol_reached_at_cycle": eol_cycle,
        "fade_rate_per_cycle": {
            "early_20pct_mean": float(np.mean(early_rate)) if len(early_rate) else None,
            "late_20pct_mean": float(np.mean(late_rate)) if len(late_rate) else None,
            "overall_mean": float(np.mean(fade_rate)) if len(fade_rate) else None,
        },
        "fade_accelerates_near_eol": (
            abs(float(np.mean(late_rate))) > abs(float(np.mean(early_rate)))
            if len(early_rate) and len(late_rate) else None
        ),
        "mean_voltage_drift": {
            "first_cycle": float(mean_voltage[0]), "last_cycle": float(mean_voltage[-1]),
            "delta": float(mean_voltage[-1] - mean_voltage[0]),
        },
        "peak_temperature_drift": {
            "first_cycle": float(peak_temp[0]), "last_cycle": float(peak_temp[-1]),
            "delta": float(peak_temp[-1] - peak_temp[0]),
        },
        "capacity_sequence": capacities.tolist(),
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    results = {}
    with zipfile.ZipFile(DATA_ZIP) as z:
        for name in BATTERIES:
            print(f"{name}: loading and analyzing...")
            cycles = load_battery(z, name)
            results[name] = analyze_battery(cycles)
            print(f"  {results[name]['n_discharge_cycles']} discharge cycles, "
                  f"fade {results[name]['total_fade_fraction']*100:.1f}%, "
                  f"EOL at cycle {results[name]['eol_reached_at_cycle']}, "
                  f"accelerates near EOL: {results[name]['fade_accelerates_near_eol']}")

    # Spread across the 4 batteries, computed once all are done.
    fades = [r["total_fade_fraction"] for r in results.values()]
    results["_spread_across_batteries"] = {
        "total_fade_fraction": {
            "mean": float(np.mean(fades)), "stdev": float(np.std(fades)),
            "min": float(np.min(fades)), "max": float(np.max(fades)),
        },
        "note": "Only zip #1 (B0005/6/7/18) analyzed; the randomized-usage "
                "dataset and the other 5 ARC zips (batteries 25-56) are "
                "explicitly out of scope this round -- see module docstring.",
    }

    with open(OUT_PATH, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nWritten to {OUT_PATH}")


if __name__ == "__main__":
    main()
