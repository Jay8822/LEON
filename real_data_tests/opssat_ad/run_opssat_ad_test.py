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

Rate-of-change extension (SPEC.md's "Rate-of-change sense
(stack-wide)" section, added alongside this), agreed with Jay before
building:

- Jump size is a rate, |value change| / |time change| in seconds, not
  a raw sample-to-sample delta. Checked directly: segments.csv's
  sampling interval is constant within a fragment but varies between
  fragments for the same channel (1s for some, 5s for others,
  confirmed from real timestamps) -- a raw delta over 5 seconds isn't
  comparable to one over 1 second for the same physical rate of
  change.
- Per channel, per setting, the jump limit is the same percentile of
  nominal training fragments' own extreme jump rate (its single
  biggest consecutive-sample rate) as the matching level setting --
  95th for STRICT, 99th for LOOSE -- same method as the level
  thresholds, just applied to rate instead of value. Fixed before any
  test-split result is looked at; never adjusted afterwards.
- SPEC.md's cross-check (did a related channel/agent also move in the
  same window) can't be exercised here at all: every OPSSAT-AD
  fragment is a single channel in isolation, so there's nothing else
  to corroborate against within one fragment. Every jump-check hit on
  this dataset is therefore, by construction, uncorroborated -- it can
  only ever be "logged for investigation," never "flagged." Reported
  plainly as untested, not worked around. The cross-check itself gets
  tested later against ESA-ADB, which records multiple channels at
  the same time.
- Nominal fragments the jump check flags are counted as false LOGS,
  not false alarms -- that word stays for the level check's output,
  which really can reach "flagged." Keeps the severity vocabulary
  honest.
- GRACIE's own code is not touched in this pass.

Run from the repo root, after download_opssat_ad.py:

    python -m real_data_tests.opssat_ad.run_opssat_ad_test
"""

import csv
import math
import os
from collections import defaultdict
from datetime import datetime

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
        self.timestamps = []

    def extreme_jump_rate(self):
        """This fragment's single biggest consecutive-sample rate of
        change, in value-units per second. None if it has fewer than
        two samples, or every consecutive pair shares a timestamp
        (rate undefined)."""
        rates = []
        for i in range(len(self.values) - 1):
            dt = (self.timestamps[i + 1] - self.timestamps[i]).total_seconds()
            if dt == 0:
                continue
            rates.append(abs(self.values[i + 1] - self.values[i]) / dt)
        return max(rates) if rates else None

    def max_jump_rate_exceeds(self, limit):
        for i in range(len(self.values) - 1):
            dt = (self.timestamps[i + 1] - self.timestamps[i]).total_seconds()
            if dt == 0:
                continue
            if abs(self.values[i + 1] - self.values[i]) / dt > limit:
                return True
        return False


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
            frag.timestamps.append(
                datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            )
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


def derive_jump_limits(train_fragments, pct):
    """Per channel, from nominal TRAINING fragments only: the pct
    percentile of each fragment's own extreme jump rate (value-units
    per second). Same method as derive_thresholds(), applied to rate
    instead of raw value -- see module docstring."""
    extremes = defaultdict(list)
    for frag in train_fragments:
        if frag.anomalous:
            continue
        rate = frag.extreme_jump_rate()
        if rate is not None:
            extremes[frag.channel].append(rate)

    limits = {}
    for channel in extremes:
        limits[channel] = {
            "limit": percentile(extremes[channel], pct),
            "n_nominal_train_fragments": len(extremes[channel]),
        }
    return limits


def jump_flagged(fragment, jump_limits):
    channel_limit = jump_limits.get(fragment.channel)
    if channel_limit is None:
        return False
    return fragment.max_jump_rate_exceeds(channel_limit["limit"])


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


def classify_shape(fragment):
    """Manual characterisation, not a dataset label (OPSSAT-AD has no
    anomaly-type field) -- SPEC.md's expected finding ("sudden spikes
    caught, slow drift missed") can't be read off a column. Heuristic:
    a fragment whose single biggest step between consecutive samples
    is large relative to its own overall spread looks spike-like;
    otherwise it looks more like a gradual drift."""
    values = fragment.values
    if len(values) < 2:
        return "drift-like"
    spread = max(values) - min(values)
    if spread == 0:
        return "drift-like"
    biggest_step = max(abs(values[i + 1] - values[i]) for i in range(len(values) - 1))
    return "spike-like" if biggest_step / spread > 0.5 else "drift-like"


def characterise_misses(missed_fragments):
    spike_like = sum(1 for f in missed_fragments if classify_shape(f) == "spike-like")
    drift_like = len(missed_fragments) - spike_like
    return spike_like, drift_like


def score_with_jump_check(test_fragments, thresholds, jump_limits):
    """Per channel: among anomalous fragments, caught by the level
    check only, the jump check only, either, or missed by both. Among
    nominal fragments, false alarms (level) vs. false logs (jump) --
    kept as separate words, since only the level check can ever reach
    "flagged" here (see module docstring on why the cross-check can't
    run on this dataset)."""
    per_channel = defaultdict(lambda: {
        "caught_level_only": 0, "caught_jump_only": 0, "caught_both": 0,
        "missed_both": 0, "false_alarm_level": 0, "false_log_jump": 0, "quiet_both": 0,
    })
    missed_by_level = []

    for frag in test_fragments:
        level_hit = flagged(frag, thresholds)
        jump_hit = jump_flagged(frag, jump_limits)
        bucket = per_channel[frag.channel]

        if frag.anomalous:
            if not level_hit:
                missed_by_level.append(frag)
            if level_hit and not jump_hit:
                bucket["caught_level_only"] += 1
            elif jump_hit and not level_hit:
                bucket["caught_jump_only"] += 1
            elif level_hit and jump_hit:
                bucket["caught_both"] += 1
            else:
                bucket["missed_both"] += 1
        else:
            if level_hit:
                bucket["false_alarm_level"] += 1
            if jump_hit:
                bucket["false_log_jump"] += 1
            if not level_hit and not jump_hit:
                bucket["quiet_both"] += 1

    return per_channel, missed_by_level


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


def print_jump_scorecard(label, per_channel, jump_limits, missed_by_level):
    print(f"\n--- {label} -- level + jump-check scorecard (threshold-based detection) ---")
    print("(threshold-based detection approach, not GRACIE's own code -- see module docstring)")
    print("(jump-check hits here are logged only, never flagged: the cross-check needs a "
          "second channel, which single-channel OPSSAT-AD fragments don't have)")

    totals = {k: 0 for k in [
        "caught_level_only", "caught_jump_only", "caught_both", "missed_both",
        "false_alarm_level", "false_log_jump", "quiet_both",
    ]}
    for channel in sorted(per_channel):
        b = per_channel[channel]
        jl = jump_limits.get(channel)
        for k in totals:
            totals[k] += b[k]
        caught_either = b["caught_level_only"] + b["caught_jump_only"] + b["caught_both"]
        limit_str = f"{jl['limit']:.6g}/s (from {jl['n_nominal_train_fragments']} fragments)" if jl else "n/a"
        print(
            f"  {channel}: caught_either={caught_either} "
            f"(level_only={b['caught_level_only']} jump_only={b['caught_jump_only']} "
            f"both={b['caught_both']}) missed_both={b['missed_both']} "
            f"false_alarm_level={b['false_alarm_level']} false_log_jump={b['false_log_jump']} "
            f"quiet_both={b['quiet_both']} (jump limit={limit_str})"
        )
    caught_either_total = totals["caught_level_only"] + totals["caught_jump_only"] + totals["caught_both"]
    print(
        f"  TOTAL: caught_either={caught_either_total} "
        f"(level_only={totals['caught_level_only']} jump_only={totals['caught_jump_only']} "
        f"both={totals['caught_both']}) missed_both={totals['missed_both']} "
        f"false_alarm_level={totals['false_alarm_level']} false_log_jump={totals['false_log_jump']} "
        f"quiet_both={totals['quiet_both']}"
    )

    spike_caught, spike_total, drift_caught, drift_total = 0, 0, 0, 0
    for frag in missed_by_level:
        shape = classify_shape(frag)
        caught_now = jump_flagged(frag, jump_limits)
        if shape == "spike-like":
            spike_total += 1
            spike_caught += caught_now
        else:
            drift_total += 1
            drift_caught += caught_now
    print(
        f"  Of the fragments the LEVEL check missed: "
        f"spike-like {spike_caught}/{spike_total} now caught by the jump check, "
        f"drift-like {drift_caught}/{drift_total} now caught by the jump check."
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

        # high_pct doubles as the jump-limit percentile for this setting
        # (95 for STRICT, 99 for LOOSE) -- same pairing used throughout.
        jump_limits = derive_jump_limits(train_fragments, high_pct)
        combined_per_channel, missed_by_level = score_with_jump_check(
            test_fragments, thresholds, jump_limits
        )
        print_jump_scorecard(label, combined_per_channel, jump_limits, missed_by_level)


if __name__ == "__main__":
    main()
