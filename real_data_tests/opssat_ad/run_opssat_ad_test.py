# real_data_tests/opssat_ad/run_opssat_ad_test.py
# Added 2026-10-23 — Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""First real-data test against OPSSAT-AD (HANDOVER.md task 4,
SPEC.md's "Real-data testing" section).

This tests the single-reading threshold-based detection approach
GRACIE uses -- NOT GRACIE's actual code. GRACIE's real FAULT logic
needs two channels at once (temp_c AND radiation); OPSSAT-AD's 2,123
labelled fragments are each a single channel in isolation, so that
two-field condition can never be exercised from this data at all.
Every heading and summary line below says "threshold-based
detection", never "GRACIE scored X" -- agreed with Jay before
building, see "Ccode update.txt" history for task 4.

Dataset: Ruszczak, B., Kotowski, K., Nalepa, J. & Evans, D.
"OPSSAT-AD — anomaly detection dataset for satellite telemetry"
(2024). https://doi.org/10.5281/zenodo.12588359. Licence: CC-BY-4.0.
Companion paper: Ruszczak, Kotowski, Nalepa & Evans, "The OPS-SAT
benchmark for detecting anomalies in satellite telemetry,"
arXiv:2407.04730 (2024).

Design, agreed with Jay for this first pass:

- None of the 9 channels (3 magnetometer: CADC0872-4, 6 photodiode:
  CADC0884-94) are temperature or radiation -- confirmed by actually
  inspecting the downloaded file's value ranges (magnetometer values
  are ~1e-5 scale, photodiode values are 0-1.57, i.e. plausibly
  radians). No channel is relabelled as "temperature" or "radiation";
  all 9 are tested independently and reported per-channel.
- GRACIE's real numbers (55, 40, 50, 30) are calibrated to a
  fictional Celsius/radiation scale that has no relationship to these
  channels' values, so they are not used here at all. Thresholds are
  instead derived statistically, per channel, from that channel's own
  training-split nominal data -- never from the test split, and never
  adjusted after seeing test-split results.
- Two-sided: a fault can be a reading dropping abnormally low, not
  only rising (SPEC.md: "anything that isn't normal is flagged"), so
  each channel gets both a high line and a low line.
- Threshold granularity matches scoring granularity. A fragment is
  scored as flagged if ANY sample in it crosses a line, so thresholds
  are derived from each nominal training FRAGMENT's own extremes (its
  max, for the high line; its min, for the low line) -- not from
  individual nominal samples, which would flood false alarms, since
  almost every fragment contains at least one sample above a
  sample-level 99th percentile.
- Two settings, fixed here before any test-split result is looked at:
  STRICT (95th percentile of nominal training fragment-maxes for the
  high line, 5th percentile of fragment-mins for the low line -- a
  closer line, so more sensitive, more false alarms) and LOOSE (99th
  / 1st -- a further line, so less sensitive, fewer false alarms).
  Both are reported side by side. Neither is tuned afterwards.
- Segments are independent fragments, not a continuous stream: no
  state carries between them.
- Scored per fragment, matching the dataset's own granularity: its
  "label" column is constant across every row of a given segment
  (verified directly -- zero segments had more than one distinct
  label value across their rows). The column actually holds four
  values, not a plain nominal/anomaly binary: "anomaly" (434
  segments, matching the paper's stated anomaly count exactly) plus
  three nominal sub-categories "a2"/"a3"/"a4" (738 + 871 + 80 = 1,689,
  matching the paper's stated nominal count). Only "anomaly" is
  treated as the positive class here; a2/a3/a4 are all nominal.
- Uses the dataset's own provided train/test split (the "train"
  column): 1,594 train / 529 test, confirmed directly from the file
  (the paper's own prose summary says 1,494/629, which doesn't match
  the file and isn't used here -- the file is authoritative).

Run from the repo root, after download_opssat_ad.py:

    python -m real_data_tests.opssat_ad.run_opssat_ad_test
"""

import csv
import math
import os
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SEGMENTS_CSV = os.path.join(DATA_DIR, "segments.csv")

# Fixed in advance, before any test-split result is looked at. Not
# tuned afterwards -- see module docstring.
SETTINGS = {
    "STRICT (95th/5th percentile)": (95, 5),
    "LOOSE (99th/1st percentile)": (99, 1),
}


def percentile(values, pct):
    """Linear-interpolation percentile (numpy's default convention),
    implemented directly since numpy isn't a dependency here."""
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (pct / 100) * (len(s) - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


class Fragment:
    def __init__(self, segment_id, channel, anomalous, is_train):
        self.segment_id = segment_id
        self.channel = channel
        self.anomalous = anomalous
        self.is_train = is_train
        self.values = []


def load_fragments():
    fragments = {}
    with open(SEGMENTS_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            seg_id = row["segment"]
            frag = fragments.get(seg_id)
            if frag is None:
                frag = Fragment(
                    segment_id=seg_id,
                    channel=row["channel"],
                    anomalous=(row["label"] == "anomaly"),
                    is_train=(row["train"] == "1"),
                )
                fragments[seg_id] = frag
            frag.values.append(float(row["value"]))
    return list(fragments.values())


def derive_thresholds(train_fragments, high_pct, low_pct):
    """Per channel, from nominal TRAINING fragments only: the high_pct
    percentile of fragment maxima (high line) and the low_pct
    percentile of fragment minima (low line)."""
    maxima = defaultdict(list)
    minima = defaultdict(list)
    for frag in train_fragments:
        if frag.anomalous:
            continue
        maxima[frag.channel].append(max(frag.values))
        minima[frag.channel].append(min(frag.values))

    thresholds = {}
    for channel in maxima:
        thresholds[channel] = {
            "high": percentile(maxima[channel], high_pct),
            "low": percentile(minima[channel], low_pct),
            "n_nominal_train_fragments": len(maxima[channel]),
        }
    return thresholds


def flagged(fragment, thresholds):
    t = thresholds[fragment.channel]
    return any(v > t["high"] or v < t["low"] for v in fragment.values)


def score(test_fragments, thresholds):
    """Per channel and overall: caught / missed / false_alarm / quiet
    (true negative) counts, scored per fragment."""
    per_channel = defaultdict(lambda: {"caught": 0, "missed": 0, "false_alarm": 0, "quiet": 0})
    missed_fragments = []

    for frag in test_fragments:
        is_flagged = flagged(frag, thresholds)
        bucket = per_channel[frag.channel]
        if frag.anomalous and is_flagged:
            bucket["caught"] += 1
        elif frag.anomalous and not is_flagged:
            bucket["missed"] += 1
            missed_fragments.append(frag)
        elif not frag.anomalous and is_flagged:
            bucket["false_alarm"] += 1
        else:
            bucket["quiet"] += 1

    return per_channel, missed_fragments


def characterise_misses(missed_fragments):
    """Manual characterisation, not a dataset label (OPSSAT-AD has no
    anomaly-type field) -- SPEC.md's expected finding ("sudden spikes
    caught, slow drift missed") can't be read off a column. Heuristic:
    a fragment whose single biggest step between consecutive samples
    is large relative to its own overall spread looks spike-like;
    otherwise it looks more like a gradual drift."""
    spike_like, drift_like = 0, 0
    for frag in missed_fragments:
        values = frag.values
        if len(values) < 2:
            drift_like += 1
            continue
        spread = max(values) - min(values)
        if spread == 0:
            drift_like += 1
            continue
        biggest_step = max(abs(values[i + 1] - values[i]) for i in range(len(values) - 1))
        if biggest_step / spread > 0.5:
            spike_like += 1
        else:
            drift_like += 1
    return spike_like, drift_like


def print_scorecard(label, per_channel, missed_fragments, thresholds):
    print(f"\n--- {label} -- threshold-based detection scorecard ---")
    print("(threshold-based detection approach, not GRACIE's own code -- see module docstring)")
    totals = {"caught": 0, "missed": 0, "false_alarm": 0, "quiet": 0}
    for channel in sorted(per_channel):
        b = per_channel[channel]
        t = thresholds[channel]
        for k in totals:
            totals[k] += b[k]
        print(
            f"  {channel}: caught={b['caught']} missed={b['missed']} "
            f"false_alarm={b['false_alarm']} quiet={b['quiet']} "
            f"(high={t['high']:.6g} low={t['low']:.6g}, "
            f"derived from {t['n_nominal_train_fragments']} nominal training fragments)"
        )
    print(f"  TOTAL: caught={totals['caught']} missed={totals['missed']} "
          f"false_alarm={totals['false_alarm']} quiet={totals['quiet']}")

    spike_like, drift_like = characterise_misses(missed_fragments)
    print(
        f"  Missed anomalies, manually characterised by shape (heuristic, not a "
        f"dataset label): spike-like={spike_like} drift-like={drift_like}"
    )


def main():
    if not os.path.exists(SEGMENTS_CSV):
        raise SystemExit(
            f"{SEGMENTS_CSV} not found -- run "
            "`python -m real_data_tests.opssat_ad.download_opssat_ad` first."
        )

    fragments = load_fragments()
    train_fragments = [f for f in fragments if f.is_train]
    test_fragments = [f for f in fragments if not f.is_train]

    print(f"Loaded {len(fragments)} fragments "
          f"({len(train_fragments)} train, {len(test_fragments)} test).")
    print("This is a first test against real spacecraft data, not a validation.")
    print("OPSSAT-AD -- Ruszczak, Kotowski, Nalepa & Evans (2024), "
          "https://doi.org/10.5281/zenodo.12588359, CC-BY-4.0.")

    for label, (high_pct, low_pct) in SETTINGS.items():
        thresholds = derive_thresholds(train_fragments, high_pct, low_pct)
        per_channel, missed_fragments = score(test_fragments, thresholds)
        print_scorecard(label, per_channel, missed_fragments, thresholds)


if __name__ == "__main__":
    main()
