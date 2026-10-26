# real_data_tests/esa_adb/learn_context.py
# Added 2026-10-26 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Step 3: training-only command/event -> channel correlation, for
GRACIE's new `expected_causes` input (agents/gracie.py, module
docstring point 12). Test-harness only -- the linking itself never
touches agents/ (Jay's "keep the agents lean" rule); GRACIE just gets
handed a plain set of channel names each cycle during the rerun.

Per Jay's answers:
1. Both missions, reported separately. Mission1: telecommands only
   (no events.csv exists for it -- checked directly). Mission2:
   telecommands AND events (events.csv exists there).
2. Three reaction windows, run and reported separately:
   correlation.REACTION_WINDOWS_SECONDS (1 minute, 10 minutes, 1 hour).
3. "Reliably reacts": correlation.py's shared method and bar (>=3x the
   random rate, >=10 co-occurrences, training period only).
4. Tag and report every linked command/event; never silently remove
   anything from a scorecard.

The TARGET side is each scored channel's own LEVEL crossings (using
that channel's per-setting STRICT/LOOSE threshold) in the training-
nominal portion only (labelled rows and Communication Gap excluded,
same discipline as derive_rules()) -- the same kind of event GRACIE's
new expected-cause input actually demotes from flagged to logged.

Scoped to the 8 channels already selected for scoring per mission
(select_channels(), same fixed seed) -- that's what the rerun needs;
going wider here wouldn't change what GRACIE sees.

Run from the repo root, after download_esa_adb.py:

    python -m real_data_tests.esa_adb.learn_context
"""

import csv
import io
import json
import os
import pickle
import time
import zipfile
from datetime import datetime

from real_data_tests.esa_adb.run_esa_adb_test import (
    DATA_DIR,
    RESULTS_DIR,
    MISSION_SPANS,
    CUTOFF_FRACTION,
    load_channel_series,
    load_channels_csv,
    load_labels_for_channel,
    load_anomaly_types,
    label_at,
    select_channels,
    derive_rules,
)
from real_data_tests.esa_adb.correlation import is_linked, random_control_times, REACTION_WINDOWS_SECONDS

MISSIONS_WITH_EVENTS = {"ESA-Mission2.zip"}  # checked directly -- Mission1 has no events.csv


def load_telecommand_ids(mission_zip_path, prefix):
    with zipfile.ZipFile(mission_zip_path) as z:
        reader = csv.DictReader(io.StringIO(z.read(f"{prefix}/telecommands.csv").decode()))
        return [r["Telecommand"] for r in reader]


def load_telecommand_times(mission_zip_path, prefix, telecommand_id):
    with zipfile.ZipFile(mission_zip_path) as z:
        inner_bytes = z.read(f"{prefix}/telecommands/{telecommand_id}.zip")
    with zipfile.ZipFile(io.BytesIO(inner_bytes)) as iz:
        raw = iz.read(iz.infolist()[0].filename)
    df = pickle.loads(raw)
    return [ts.timestamp() for ts in df.index.to_pydatetime()]


def load_event_times(mission_zip_path, prefix):
    """{event_id: [start_ts, ...]} -- events.csv has no channel column;
    some event ids recur with multiple (Event, StartTime, EndTime) rows."""
    with zipfile.ZipFile(mission_zip_path) as z:
        if f"{prefix}/events.csv" not in z.namelist():
            return {}
        reader = csv.DictReader(io.StringIO(z.read(f"{prefix}/events.csv").decode()))
    out = {}
    for r in reader:
        start = datetime.fromisoformat(r["StartTime"].replace("Z", "+00:00")).replace(tzinfo=None)
        out.setdefault(r["Event"], []).append(start.timestamp())
    return out


def discover_channel_context(channel, rule_values, timestamps, values, labels, cutoff,
                              telecommand_times, event_times):
    if rule_values["level_high"] is None or rule_values["level_low"] is None:
        return {"skipped": "insufficient nominal training days to derive a level threshold"}

    high, low = rule_values["level_high"], rule_values["level_low"]
    train_crossings = []
    train_start = train_end = None
    for t, v in zip(timestamps, values):
        if t >= cutoff:
            continue
        if label_at(t, labels) is not None:
            continue
        ts = t.timestamp()
        train_start = ts if train_start is None else min(train_start, ts)
        train_end = ts if train_end is None else max(train_end, ts)
        if v > high or v < low:
            train_crossings.append(ts)
    train_crossings.sort()
    if train_start is None:
        return {"skipped": "no training-nominal samples"}

    cutoff_ts = cutoff.timestamp()
    linked = {w: {"telecommands": {}, "events": {}} for w in REACTION_WINDOWS_SECONDS}
    for window_name, window_seconds in REACTION_WINDOWS_SECONDS.items():
        controls = random_control_times(train_start, train_end)
        for tc_id, firing_times in telecommand_times.items():
            train_firings = [t for t in firing_times if t < cutoff_ts]
            if not train_firings:
                continue
            r = is_linked(train_firings, train_crossings, window_seconds, train_start, train_end, controls)
            if r["linked"]:
                linked[window_name]["telecommands"][tc_id] = r
        for ev_id, firing_times in event_times.items():
            train_firings = [t for t in firing_times if t < cutoff_ts]
            if not train_firings:
                continue
            r = is_linked(train_firings, train_crossings, window_seconds, train_start, train_end, controls)
            if r["linked"]:
                linked[window_name]["events"][ev_id] = r
    return {"linked": linked, "n_training_crossings": len(train_crossings)}


def run_mission(mission_zip):
    prefix = mission_zip.replace(".zip", "")
    path = os.path.join(DATA_DIR, mission_zip)
    results_path = os.path.join(RESULTS_DIR, f"{prefix}-context.json")

    results = {}
    if os.path.exists(results_path):
        with open(results_path) as f:
            results = json.load(f)

    channels_rows = load_channels_csv(path, prefix)
    anomaly_types = load_anomaly_types(path, prefix)
    selected = select_channels(channels_rows)
    start, end = MISSION_SPANS[mission_zip]
    cutoff = start + (end - start) * CUTOFF_FRACTION

    print(f"=== {mission_zip}: loading telecommands/events once, reused across {len(selected)} channels ===")
    telecommand_ids = load_telecommand_ids(path, prefix)
    telecommand_times = {tc: load_telecommand_times(path, prefix, tc) for tc in telecommand_ids}
    event_times = load_event_times(path, prefix) if mission_zip in MISSIONS_WITH_EVENTS else {}
    print(f"{mission_zip}: {len(telecommand_times)} telecommands, {len(event_times)} events loaded")

    for channel in selected:
        if channel in results:
            print(f"{channel}: already done, skipping (resume).")
            continue
        t0 = time.time()
        try:
            timestamps, values = load_channel_series(path, prefix, channel)
            labels = load_labels_for_channel(path, prefix, anomaly_types, channel)
            rules = derive_rules(timestamps, values, labels, cutoff)
            per_setting = {}
            for setting_name, rule_values in rules.items():
                per_setting[setting_name] = discover_channel_context(
                    channel, rule_values, timestamps, values, labels, cutoff,
                    telecommand_times, event_times,
                )
            results[channel] = per_setting
        except Exception as exc:
            results[channel] = {"error": repr(exc)}
        results[channel]["elapsed_seconds"] = time.time() - t0

        os.makedirs(RESULTS_DIR, exist_ok=True)
        with open(results_path, "w") as f:
            json.dump(results, f, default=str, indent=2)
        print(f"{channel}: done in {results[channel]['elapsed_seconds']:.1f}s -- checkpointed.")

    print(f"Written to {results_path}")
    return results


def main():
    print("ESA-ADB context-checking discovery (Step 3) -- TRAINING ONLY, test-harness only.")
    for mission_zip in ["ESA-Mission1.zip", "ESA-Mission2.zip"]:
        run_mission(mission_zip)


if __name__ == "__main__":
    main()
