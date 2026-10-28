# bg_jobs/queue/job3_mars_express_kicks.py
# Added 2026-10-28 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Queue job 3 of 5 ("keep the laptop working while usage is low" --
Ccode update.txt). LOOK ONLY -- no GRACIE, no scoring, no threshold.
Measures how much each of the 33 Mars Express thermal power lines
changes shortly after a real event (a DMOP command, an FTL pointing-
period start, an EVTF eclipse start), versus a LOCAL baseline taken
immediately before that same event -- not a global/fixed reference,
so a slow, multi-hundred-day orbital-distance trend (LTDATA's
solarconstantmars) cannot itself be mistaken for the event's own
effect, by construction (the baseline window is minutes-to-hours,
negligible next to a ~687-day Mars year). LTDATA's solarconstantmars
at each event's own time is additionally reported alongside every
measurement, as a diagnostic a human can check for any leftover
orbital correlation in the "excess" numbers -- not used to adjust
them further.

Method fixed here, in advance, before any measurement is run (same
discipline as every other round this session):
- THREE fixed window sizes: 5 min, 30 min, 2 hour. Baseline window
  length always equals the reaction window length being measured,
  taken immediately before the event.
- Event types, decided by a fixed, non-reaction-based rule (frequency
  alone, never by which ones react more): EVTF's two eclipse markers
  (MAR_PENUMBRA_START, MAR_UMBRA_START); every distinct FTL pointing
  `type` value; DMOP's TOP 10 most frequent `subsystem` codes by raw
  firing count across the full training period (a pre-committed,
  defensible cutoff, not cherry-picked after seeing any reaction).
- Measurement: per event instance, per power line, excess = mean(power
  in the reaction window) - mean(power in the baseline window).
  Reported per (event type, power line, window size): mean/median/
  stdev of excess, sample size (how many event instances had enough
  data in both windows to compute it).

STREAMED: each ~600MB power--*.csv is read via pandas chunksize, never
loaded whole (this machine has 6GB RAM, has crashed from memory
pressure multiple times this session). Context files (DMOP/FTL/EVTF/
LTDATA, a few MB each) are loaded fully -- safe.

Checkpointed per YEAR (3 training years) -- resumable; years are
reported separately, not merged, to keep this simple and correct.

No anomaly labels exist in this dataset (confirmed in
real_data_tests/mars_express_power/PROFILE.md) -- this produces a
plain magnitude/duration measurement, never a detection verdict.

Run from the repo root:
    python -m bg_jobs.queue.job3_mars_express_kicks
"""
import csv
import io
import json
import os
import statistics
import zipfile
from collections import Counter

import numpy as np
import pandas as pd

DATA_ZIP = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..",
    "real_data_tests", "mars_express_power", "data", "mars-express-power-3years.zip",
)
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
OUT_PATH = os.path.join(OUT_DIR, "job3_mars_express_kicks.json")

TRAIN_YEARS = ["2008-08-22_2010-07-10", "2010-07-10_2012-05-27", "2012-05-27_2014-04-14"]
WINDOW_SECONDS = {"5min": 300.0, "30min": 1800.0, "2hour": 7200.0}
DMOP_TOP_N = 10  # fixed in advance, by raw firing frequency alone -- see module docstring
CHUNK_ROWS = 500_000


def _read_csv_member(z, member):
    with z.open(member) as f:
        return pd.read_csv(io.TextIOWrapper(f, encoding="utf-8"))


def load_events_for_year(z, year):
    """Returns {event_type_label: sorted numpy array of ut_ms times}.
    DMOP's top-N codes are picked HERE, from this year's own raw
    firing counts alone -- before anything about power lines is
    touched."""
    dmop = _read_csv_member(z, f"mars-express-power-3years/train_set/context--{year}--dmop.csv")
    ftl = _read_csv_member(z, f"mars-express-power-3years/train_set/context--{year}--ftl.csv")
    evtf = _read_csv_member(z, f"mars-express-power-3years/train_set/context--{year}--evtf.csv")

    events = {}
    for desc in ("MAR_PENUMBRA_START", "MAR_UMBRA_START"):
        times = evtf.loc[evtf["description"] == desc, "ut_ms"].to_numpy()
        events[f"evtf_{desc}"] = np.sort(times)

    for ftl_type in sorted(ftl["type"].unique()):
        times = ftl.loc[ftl["type"] == ftl_type, "utb_ms"].to_numpy()
        events[f"ftl_{ftl_type}"] = np.sort(times)

    top_codes = [code for code, _ in Counter(dmop["subsystem"]).most_common(DMOP_TOP_N)]
    for code in top_codes:
        times = dmop.loc[dmop["subsystem"] == code, "ut_ms"].to_numpy()
        events[f"dmop_{code}"] = np.sort(times)

    return events


def load_ltdata_for_year(z, year):
    ltdata = _read_csv_member(z, f"mars-express-power-3years/train_set/context--{year}--ltdata.csv")
    return ltdata["ut_ms"].to_numpy(), ltdata["solarconstantmars"].to_numpy()


def _accumulate_chunk(chunk_t, chunk_power, events, window_ms, acc):
    """acc[event_type][power_line] -> {"baseline_sum":[...per-instance...], "baseline_count":[...],
    "reaction_sum":[...], "reaction_count":[...]} numpy arrays, one slot per event instance.
    Vectorised per chunk via searchsorted, not a Python loop per row."""
    for etype, times in events.items():
        if len(times) == 0:
            continue
        # Reaction: this row's nearest event AT OR BEFORE it, if within window_ms after it.
        idx_r = np.searchsorted(times, chunk_t, side="right") - 1
        valid_r = (idx_r >= 0)
        if valid_r.any():
            dt_r = chunk_t[valid_r] - times[idx_r[valid_r]]
            in_r = dt_r <= window_ms
            rows_r = np.nonzero(valid_r)[0][in_r]
            inst_r = idx_r[valid_r][in_r]
        else:
            rows_r = np.array([], dtype=int)
            inst_r = np.array([], dtype=int)
        # Baseline: this row's nearest event AT OR AFTER it, if within window_ms before it.
        idx_b = np.searchsorted(times, chunk_t, side="left")
        valid_b = (idx_b < len(times))
        if valid_b.any():
            dt_b = times[idx_b[valid_b]] - chunk_t[valid_b]
            in_b = dt_b <= window_ms
            rows_b = np.nonzero(valid_b)[0][in_b]
            inst_b = idx_b[valid_b][in_b]
        else:
            rows_b = np.array([], dtype=int)
            inst_b = np.array([], dtype=int)

        bucket = acc.setdefault(etype, {})
        n_inst = len(times)
        for col in chunk_power.columns:
            vals = chunk_power[col].to_numpy()
            d = bucket.setdefault(col, {
                "baseline_sum": np.zeros(n_inst), "baseline_count": np.zeros(n_inst, dtype=int),
                "reaction_sum": np.zeros(n_inst), "reaction_count": np.zeros(n_inst, dtype=int),
            })
            if len(rows_r):
                np.add.at(d["reaction_sum"], inst_r, vals[rows_r])
                np.add.at(d["reaction_count"], inst_r, 1)
            if len(rows_b):
                np.add.at(d["baseline_sum"], inst_b, vals[rows_b])
                np.add.at(d["baseline_count"], inst_b, 1)


def process_year(z, year):
    print(f"  loading context files for {year}...")
    events = load_events_for_year(z, year)
    ltdata_t, ltdata_solar = load_ltdata_for_year(z, year)
    print(f"  event types: { {k: len(v) for k, v in events.items()} }")

    power_member = f"mars-express-power-3years/train_set/power--{year}.csv"
    power_cols = None
    results_by_window = {}

    for window_name, window_seconds in WINDOW_SECONDS.items():
        window_ms = window_seconds * 1000.0
        acc = {}
        with z.open(power_member) as f:
            reader = pd.read_csv(io.TextIOWrapper(f, encoding="utf-8"), chunksize=CHUNK_ROWS)
            for chunk in reader:
                if power_cols is None:
                    power_cols = [c for c in chunk.columns if c != "ut_ms"]
                chunk_t = chunk["ut_ms"].to_numpy()
                _accumulate_chunk(chunk_t, chunk[power_cols], events, window_ms, acc)

        window_result = {}
        for etype, cols in acc.items():
            window_result[etype] = {}
            for col, d in cols.items():
                valid = (d["baseline_count"] > 0) & (d["reaction_count"] > 0)
                if not valid.any():
                    continue
                baseline_mean = d["baseline_sum"][valid] / d["baseline_count"][valid]
                reaction_mean = d["reaction_sum"][valid] / d["reaction_count"][valid]
                excess = reaction_mean - baseline_mean
                window_result[etype][col] = {
                    "n_instances": int(valid.sum()),
                    "mean_excess": float(np.mean(excess)),
                    "median_excess": float(np.median(excess)),
                    "stdev_excess": float(np.std(excess)) if len(excess) > 1 else 0.0,
                }
        results_by_window[window_name] = window_result
        print(f"  {year} / {window_name}: done, {len(acc)} event types measured")

    # LTDATA solar-constant range this year, as a diagnostic alongside
    # the measurements above -- not used to adjust them (see docstring).
    solar_context = {
        "solarconstantmars_min": float(np.min(ltdata_solar)),
        "solarconstantmars_max": float(np.max(ltdata_solar)),
        "solarconstantmars_mean": float(np.mean(ltdata_solar)),
    }

    return {"by_window": results_by_window, "ltdata_solar_context": solar_context}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    results = {}
    if os.path.exists(OUT_PATH):
        with open(OUT_PATH) as f:
            results = json.load(f)
        print(f"resuming -- {len(results)} year(s) already done")

    with zipfile.ZipFile(DATA_ZIP) as z:
        for year in TRAIN_YEARS:
            if year in results:
                print(f"{year}: already done, skipping (resume)")
                continue
            print(f"=== {year} ===")
            results[year] = process_year(z, year)
            with open(OUT_PATH, "w") as f:
                json.dump(results, f, indent=2, default=str)
            print(f"{year}: checkpointed")

    print(f"\nAll {len(TRAIN_YEARS)} years done. Written to {OUT_PATH}")


if __name__ == "__main__":
    main()
