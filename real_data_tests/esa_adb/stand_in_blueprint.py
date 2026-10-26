# real_data_tests/esa_adb/stand_in_blueprint.py
# Added 2026-10-26 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Step 4's "learned stand-in blueprint" -- NOT a real blueprint
(SPEC.md's Blueprint comes from the people who built the craft; this
is a test-harness substitute, labelled as such everywhere, built
from the TRAINING period only, never from test data). Test-harness
only -- none of this lives in agents/ (Jay's "keep the agents lean"
rule): the output is a plain noise-band number per channel and a
plain tuple of candidate linked-channel names, handed to
ChannelRule.linked_channels exactly like any other rule-book value.

Two pieces, both cheap and look-only (no GracieAgent):

1. Normal noise band, per channel: median and IQR of the TRAINING-
   NOMINAL sample-to-sample absolute change (labelled rows and
   Communication Gap excluded, same discipline as derive_rules() and
   measure_drift.py). Jay's agreed statistic (Step 4, ambiguity 2).
   Computed for every MONITORED channel in both missions (105 total),
   not just the 16 scored ones -- cheap, so go wide.

2. "Which channels jitter together": for each ordered pair of
   monitored channels in the SAME mission, correlate channel A's "big
   change" timestamps (a delta exceeding A's own noise-band median +
   IQR -- a simple, clearly-labelled derived cutoff, my own
   construction since Jay's noise-band answer didn't specify a
   cutoff for THIS purpose; flagged plainly here and in the write-up)
   against channel B's, using correlation.py's shared method and bar
   (Jay's Step 4, ambiguity 3: same method and bar as Step 3.3), for
   each of the three reaction windows. A candidate link is wired into
   the rerun's ChannelRule.linked_channels ONLY when both channels are
   among that mission's 16 scored channels -- outside that set it's
   reported but inert (no GracieAgent state to attach to).

Run from the repo root, after download_esa_adb.py:

    python -m real_data_tests.esa_adb.stand_in_blueprint
"""

import json
import os
import time

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
    select_channels,
)
from real_data_tests.esa_adb.correlation import is_linked, random_control_times, REACTION_WINDOWS_SECONDS

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def iqr(values):
    if not values:
        return None
    return percentile(values, 75) - percentile(values, 25)


def noise_band_and_big_changes(mission_zip, prefix, channel, anomaly_types, cutoff):
    """Returns (noise_median, noise_iqr, big_change_timestamps_sorted,
    train_start_ts, train_end_ts) -- all from the TRAINING-NOMINAL
    portion only."""
    timestamps, values = load_channel_series(os.path.join(DATA_DIR, mission_zip), prefix, channel)
    labels = load_labels_for_channel(os.path.join(DATA_DIR, mission_zip), prefix, anomaly_types, channel)

    deltas = []
    train_ts, train_vs = [], []
    for t, v in zip(timestamps, values):
        if t >= cutoff:
            continue
        if label_at(t, labels) is not None:
            continue  # excluded -- labelled or Communication Gap, not normal behaviour
        train_ts.append(t.timestamp())
        train_vs.append(v)

    for i in range(1, len(train_vs)):
        deltas.append(abs(train_vs[i] - train_vs[i - 1]))

    noise_median = percentile(deltas, 50) if deltas else None
    noise_iqr = iqr(deltas)
    big_cutoff = (noise_median + noise_iqr) if (noise_median is not None and noise_iqr is not None) else None

    big_changes = []
    if big_cutoff is not None:
        for i in range(1, len(train_vs)):
            if abs(train_vs[i] - train_vs[i - 1]) > big_cutoff:
                big_changes.append(train_ts[i])

    return {
        "noise_median": noise_median,
        "noise_iqr": noise_iqr,
        "big_change_cutoff": big_cutoff,
        "n_big_changes_training": len(big_changes),
        "_big_change_timestamps": sorted(big_changes),
        "_train_span_ts": (train_ts[0], train_ts[-1]) if train_ts else None,
    }


def build_mission(mission_zip, channels_to_report):
    prefix = mission_zip.replace(".zip", "")
    path = os.path.join(DATA_DIR, mission_zip)
    channels_rows = load_channels_csv(path, prefix)
    anomaly_types = load_anomaly_types(path, prefix)
    monitored = [r["Channel"] for r in channels_rows if r["Target"] == "YES"]
    start, end = MISSION_SPANS[mission_zip]
    cutoff = start + (end - start) * CUTOFF_FRACTION

    print(f"=== {mission_zip}: noise band for {len(monitored)} monitored channels ===")
    per_channel = {}
    for channel in monitored:
        t0 = time.time()
        try:
            per_channel[channel] = noise_band_and_big_changes(mission_zip, prefix, channel, anomaly_types, cutoff)
        except Exception as exc:
            per_channel[channel] = {"error": repr(exc)}
        per_channel[channel]["elapsed_seconds"] = time.time() - t0

    scored_set = set(channels_to_report)
    train_span = next((v["_train_span_ts"] for v in per_channel.values() if v.get("_train_span_ts")), None)
    controls_by_window = {
        w: random_control_times(train_span[0], train_span[1]) for w in REACTION_WINDOWS_SECONDS
    } if train_span else {}

    print(f"=== {mission_zip}: jitter-together correlation among {len(scored_set)} scored channels ===")
    jitter_links = {w: {} for w in REACTION_WINDOWS_SECONDS}
    for a in scored_set:
        if "error" in per_channel.get(a, {}):
            continue
        a_times = per_channel[a]["_big_change_timestamps"]
        for b in monitored:
            if b == a or "error" in per_channel.get(b, {}):
                continue
            b_times = per_channel[b]["_big_change_timestamps"]
            for window_name, window_seconds in REACTION_WINDOWS_SECONDS.items():
                result = is_linked(a_times, b_times, window_seconds,
                                    train_span[0], train_span[1], controls_by_window[window_name])
                if result["linked"]:
                    jitter_links[window_name].setdefault(a, []).append({"linked_to": b, **result})

    noise_bands = {
        ch: {k: v for k, v in r.items() if not k.startswith("_") and k != "elapsed_seconds"}
        for ch, r in per_channel.items()
    }
    return {
        "noise_bands": noise_bands,
        "jitter_together": jitter_links,
    }


def main():
    print("ESA-ADB learned stand-in blueprint (Step 4) -- NOT a real blueprint. LOOK ONLY, no GracieAgent.")
    os.makedirs(RESULTS_DIR, exist_ok=True)
    for mission_zip in ["ESA-Mission1.zip", "ESA-Mission2.zip"]:
        prefix = mission_zip.replace(".zip", "")
        path = os.path.join(DATA_DIR, mission_zip)
        channels_rows = load_channels_csv(path, prefix)
        selected = select_channels(channels_rows)
        result = build_mission(mission_zip, selected)
        out_path = os.path.join(RESULTS_DIR, f"{prefix}-stand-in.json")
        with open(out_path, "w") as f:
            json.dump(result, f, default=str, indent=2)
        print(f"{mission_zip}: written to {out_path}")


if __name__ == "__main__":
    main()
