# real_data_tests/esa_adb/run_esa_adb_test.py
# Added 2026-10-25 — Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""First real-data test against ESA-ADB, run through the REAL
GracieAgent (any-sensor rule book) via process_readings() -- not a
separate batch script, unlike OPSSAT-AD's first pass. Built on that
method, with changes agreed for this dataset's shape (see
"Ccode update.txt" history).

Dataset: De Canio, G., Kotowski, K. & Haskamp, C. et al. "ESA Anomaly
Dataset" (2024). https://doi.org/10.5281/zenodo.12528696 (CC BY 3.0
IGO). Companion paper: Kotowski et al., "European Space Agency
Benchmark for Anomaly Detection in Satellite Telemetry,"
arXiv:2406.17826 (2024). Missions 1 and 2 only -- Mission3 isn't part
of the benchmark and was never downloaded (too few anomalies, too
many communication gaps, per the paper).

FIRST TEST AGAINST REAL SPACECRAFT DATA. NOT A VALIDATION.

Design, agreed with Jay before building:

1. One shared calendar cutoff date PER MISSION (not a per-channel
   70/30 split): fixed at 70% of that mission's own overall span
   (MISSION_SPANS below, taken directly from the full-channel profile
   run earlier, not re-derived here). Reason: channels are recorded
   simultaneously and events span many channels, so a shared date
   keeps each event wholly on one side and keeps timing aligned for
   whenever cross-checks get built.
2. Training-only derivation excludes ALL labelled time (Anomaly and
   Rare Event) -- same principle as OPSSAT-AD's nominal-only
   derivation. Communication Gap rows are dropped entirely, train and
   test alike -- a gap isn't a reading at all.
3. No fragment boundaries exist in this data (continuous recordings,
   not pre-cut segments), so derivation chunks the training-nominal
   portion into 1-day pseudo-fragments and takes percentiles of each
   day's own extremes -- same method OPSSAT-AD and the simulated
   leash test use, a chosen chunk length standing in for OPSSAT-AD's
   natural fragment boundaries.
4. Anomalies and Rare Events are scored SEPARATELY and reported
   honestly. GRACIE's level/jump/leash senses have no way to tell them
   apart -- both are just "crossed a threshold" to a detector that
   only sees numbers, with no expected-cause signal available (that's
   exactly the gap jump's cross-check and leash's context-gating
   would fill, neither built yet). This does NOT claim GRACIE achieves
   "logged not flagged" for Rare Events -- it reports what actually
   happens to each category and leaves the reader to judge.
5. Jump's cross-check and leash's context-gating are out of scope --
   not implemented in agents/gracie.py (see that file's own module
   docstring, point 7), regardless of what this dataset offers.
   labels.csv's multivariate events and telecommands.csv/events.csv
   are exactly the right shape for testing them once they exist --
   noted for later, not used here.
6. Channels: 8 per mission, monitored (Target=YES) only, chosen by a
   FIXED rule before any scoring -- stratified across subsystems with
   a fixed random seed (SELECTION_SEED below), round-robining through
   subsystems so no single one dominates. No cherry-picking; the
   chosen channels are printed and written into the results file.
7. GRACIE latches level FAULT and hard-leash FAULT until cleared --
   over a 14-year (Mission1) or 3.5-year (Mission2) recording, one
   early latch would stay latched for the rest of the mission and
   wreck the scoring. clear_fault() is called at every calendar-day
   boundary in the test period, as a stand-in for a real sign-off.
   HONEST CAVEAT, found while building this: clear_fault() also
   resets the leash pull-duration clock (_ChannelState.pull_run_start)
   and its soft/hard edge-detectors -- it does NOT touch the windowed-
   slope sample history (_ChannelState.window) or jump's last-sample
   reference, so the *shape* of recent readings carries across a
   daily clear, but a drift that would only cross LEASH_HARD_DURATION_
   SECONDS by straddling a day boundary can never be scored as
   reaching hard under this methodology. Not changing GracieAgent's
   clear_fault() to behave differently -- that would be an agent
   behaviour change, explicitly out of scope -- so this is reported as
   a limitation, not quietly worked around.

8. Added 2026-10-25 (follow-up pass): two fixes, both found while
   reviewing the first run's results (see RESULTS.md's known-gap
   note).
   - The daily clear now calls `clear_fault(reset_leash_timer=False)`
     (agents/gracie.py's new option, added for exactly this) instead
     of `clear_fault()` -- the latch still clears every day, but the
     leash pull-duration clock keeps running, so point 7's limitation
     above no longer applies.
   - score_test_period() now tags every event by which sense caused
     it -- level, jump, leash, independently, plus "any" (the real
     aggregate, gracie.health_state, which DOES include jump's
     momentary bump) -- instead of reading only
     `_last_readings[channel]["severity"]`, which never reflected
     jump at all. Each cause is reported as "caught_logged" (reached
     at least WARNING) and "caught_flagged" (reached FAULT)
     separately, since jump can only ever log, level can only ever
     flag, and leash can do either.
   - Also found and fixed while rereading this for the above: point 2
     always said Communication Gap rows are "dropped entirely, train
     and test alike," but the TEST loop never actually did that --
     only derive_rules() (training) excluded them. The first run fed
     gap rows through GracieAgent during test scoring and scored
     "Communication Gap" as if it were a real labelled category.
     Mission1 only has 4 gap events total, so the effect on the first
     run's numbers is likely small, but it was never checked before
     now -- not claiming otherwise.

Window/duration choice: OPSSAT-AD's leash constants (30s window, 60s/
150s durations) are far too short for data running in years with
per-channel median sampling gaps from under a second to tens of
minutes. LEASH_WINDOW_SECONDS/SOFT/HARD below are fresh, clearly-
labelled test-fixture choices for THIS dataset's timescale (an hour,
six hours, a day) -- not derived from OPSSAT-AD, not hardware-
calibrated.

Chunked and checkpointed: one channel fully processed (both STRICT
and LOOSE settings) writes its result to results/<mission>.json
before moving to the next; already-present channels are skipped on a
re-run, so an interrupted run resumes rather than restarting. Never
more than one channel's full series in memory at a time.

Run from the repo root, after download_esa_adb.py (Missions 1+2 only):

    python -m real_data_tests.esa_adb.run_esa_adb_test
"""

import csv
import io
import json
import os
import pickle
import random
import time
import zipfile
from datetime import datetime

from real_data_tests.opssat_ad.run_opssat_ad_test import percentile

from agents.gracie import GracieAgent
from agents.gracie_rulebook import ChannelRule
from core.bus import EventBus

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

# Taken directly from the full-channel profiling pass (Job 2) -- not
# re-derived here.
MISSION_SPANS = {
    "ESA-Mission1.zip": (datetime(2000, 1, 1, 0, 0, 0), datetime(2013, 12, 31, 23, 59, 59)),
    "ESA-Mission2.zip": (datetime(2000, 1, 1, 0, 0, 0), datetime(2003, 6, 30, 23, 59, 52)),
}
CUTOFF_FRACTION = 0.70

SELECTION_SEED = 20261025
N_CHANNELS_PER_MISSION = 8

# Leash design choices for THIS dataset's timescale -- see module
# docstring. Not OPSSAT-AD's numbers, not hardware-calibrated.
LEASH_WINDOW_SECONDS = 3600.0          # 1 hour
LEASH_SOFT_DURATION_SECONDS = 21600.0  # 6 hours
LEASH_HARD_DURATION_SECONDS = 86400.0  # 24 hours

# Fixed before any test-period result is looked at. Not tuned afterwards.
SETTINGS = {"STRICT": (95, 5), "LOOSE": (99, 1)}

# Grace window around a labelled event's edges for a transition to
# still count as catching it -- same spirit as the simulated leash
# test's GRACE_SECONDS, scaled to this dataset's much longer timescale.
GRACE_SECONDS = 3600.0


def percentile_or_none(values, pct):
    return percentile(values, pct) if values else None


# --- loading -----------------------------------------------------------------

def load_channel_series(mission_zip_path, prefix, channel):
    """Returns (timestamps: list[datetime], values: list[float])."""
    with zipfile.ZipFile(mission_zip_path) as z:
        inner_bytes = z.read(f"{prefix}/channels/{channel}.zip")
    with zipfile.ZipFile(io.BytesIO(inner_bytes)) as iz:
        raw = iz.read(iz.infolist()[0].filename)
    df = pickle.loads(raw)
    series = df.iloc[:, 0]
    return list(series.index.to_pydatetime()), [float(v) for v in series.values]


def load_channels_csv(mission_zip_path, prefix):
    with zipfile.ZipFile(mission_zip_path) as z:
        return list(csv.DictReader(io.StringIO(z.read(f"{prefix}/channels.csv").decode())))


def load_labels_for_channel(mission_zip_path, prefix, anomaly_types, channel):
    """Returns a list of (category, start, end) for this channel,
    category from anomaly_types.csv's Category column ("Anomaly",
    "Rare Event", "Communication Gap")."""
    with zipfile.ZipFile(mission_zip_path) as z:
        reader = csv.DictReader(io.StringIO(z.read(f"{prefix}/labels.csv").decode()))
        rows = [r for r in reader if r["Channel"] == channel]
    out = []
    for r in rows:
        category = anomaly_types.get(r["ID"], "Unknown")
        start = datetime.fromisoformat(r["StartTime"].replace("Z", "+00:00")).replace(tzinfo=None)
        end = datetime.fromisoformat(r["EndTime"].replace("Z", "+00:00")).replace(tzinfo=None)
        out.append((category, start, end))
    return out


def load_anomaly_types(mission_zip_path, prefix):
    with zipfile.ZipFile(mission_zip_path) as z:
        reader = csv.DictReader(io.StringIO(z.read(f"{prefix}/anomaly_types.csv").decode()))
        return {r["ID"]: r["Category"] for r in reader}


# --- channel selection, fixed before any scoring ------------------------------

def select_channels(channels_rows, seed=SELECTION_SEED, n=N_CHANNELS_PER_MISSION):
    monitored = [r for r in channels_rows if r["Target"] == "YES"]
    by_subsystem = {}
    for r in monitored:
        by_subsystem.setdefault(r["Subsystem"], []).append(r["Channel"])
    subsystems = sorted(by_subsystem.keys())
    rng = random.Random(seed)
    for pool in by_subsystem.values():
        rng.shuffle(pool)

    selected = []
    i = 0
    while len(selected) < n and any(by_subsystem.values()):
        subsystem = subsystems[i % len(subsystems)]
        pool = by_subsystem[subsystem]
        if pool:
            selected.append(pool.pop())
        i += 1
    return selected


# --- derivation: 1-day pseudo-fragments, nominal training only --------------

def extreme_jump_rate(values, seconds):
    best = None
    for i in range(len(values) - 1):
        dt = seconds[i + 1] - seconds[i]
        if dt <= 0:
            continue
        rate = abs(values[i + 1] - values[i]) / dt
        if best is None or rate > best:
            best = rate
    return best


def extreme_leash_slope(values, seconds, window_seconds):
    best = None
    j = 0
    n = len(seconds)
    for i in range(n):
        while j + 1 <= i and (seconds[i] - seconds[j + 1]) >= window_seconds:
            j += 1
        dt = seconds[i] - seconds[j]
        if dt >= window_seconds:
            slope = abs(values[i] - values[j]) / dt
            if best is None or slope > best:
                best = slope
    return best


def label_at(timestamp, labels):
    """First (category, start, end) covering `timestamp`, or None."""
    for category, start, end in labels:
        if start <= timestamp <= end:
            return category
    return None


def derive_rules(timestamps, values, labels, cutoff):
    """Chunks the TRAINING + NOMINAL-only portion into calendar days,
    returns {setting_name: ChannelRule}."""
    day_max, day_min, day_jump, day_leash = {}, {}, {}, {}
    for t, v in zip(timestamps, values):
        if t >= cutoff:
            continue
        category = label_at(t, labels)
        if category is not None:
            continue  # excluded from derivation -- labelled, not nominal
        day = t.date()
        day_max.setdefault(day, []).append((t, v))

    extremes_max, extremes_min, extremes_jump, extremes_leash = [], [], [], []
    for day, pairs in day_max.items():
        pairs.sort(key=lambda p: p[0])
        day_t = [p[0] for p in pairs]
        day_v = [p[1] for p in pairs]
        if len(day_v) < 2:
            continue
        extremes_max.append(max(day_v))
        extremes_min.append(min(day_v))
        day_seconds = [t.timestamp() for t in day_t]
        jr = extreme_jump_rate(day_v, day_seconds)
        if jr is not None:
            extremes_jump.append(jr)
        ls = extreme_leash_slope(day_v, day_seconds, LEASH_WINDOW_SECONDS)
        if ls is not None:
            extremes_leash.append(ls)

    rules = {}
    for setting_name, (high_pct, low_pct) in SETTINGS.items():
        rules[setting_name] = {
            "level_high": percentile_or_none(extremes_max, high_pct),
            "level_low": percentile_or_none(extremes_min, low_pct),
            "jump_limit": percentile_or_none(extremes_jump, high_pct),
            "leash_slope_limit": percentile_or_none(extremes_leash, high_pct),
            "n_training_days": len(extremes_max),
        }
    return rules


# --- scoring: feed the test period through a REAL GracieAgent --------------

def score_test_period(channel, rule_values, timestamps, values, labels, cutoff):
    if any(rule_values[k] is None for k in
           ("level_high", "level_low", "jump_limit", "leash_slope_limit")):
        return {"rule": rule_values, "skipped": "insufficient nominal training days to derive a limit"}

    rule = ChannelRule(
        name=channel, units="u",
        level_high=rule_values["level_high"], level_low=rule_values["level_low"],
        jump_limit=rule_values["jump_limit"],
        leash_window_seconds=LEASH_WINDOW_SECONDS,
        leash_slope_limit=rule_values["leash_slope_limit"],
        leash_soft_duration_seconds=LEASH_SOFT_DURATION_SECONDS,
        leash_hard_duration_seconds=LEASH_HARD_DURATION_SECONDS,
    )
    bus = EventBus()
    gracie = GracieAgent(bus, {channel: rule})

    # Events are tagged by cause, independently, per the agreed design:
    #   level -- always reaches FAULT directly (level never sets WARNING).
    #   jump  -- always "logged" (WARNING-equivalent); jump never reaches
    #            FAULT on its own. Checked via _last_readings[...]["jump"],
    #            which was computed every cycle but never read for scoring
    #            in the first pass -- see RESULTS.md's known-gap note.
    #   leash -- can reach either WARNING (soft) or FAULT (hard); detected
    #            as a latched_severity transition that ISN'T explained by
    #            a level crossing this same cycle.
    #   any   -- the real aggregate (gracie.health_state), which DOES
    #            include jump's momentary bump, unlike latched_severity
    #            alone (the field the first pass read).
    level_events, jump_events, leash_events, any_events = [], [], [], []
    prior_latched = "NOMINAL"
    prior_aggregate = "NOMINAL"
    last_day = None

    for t, v in zip(timestamps, values):
        if t < cutoff:
            continue
        if label_at(t, labels) == "Communication Gap":
            continue  # dropped entirely, train and test alike -- not a reading at all
        day = t.date()
        if last_day is not None and day != last_day:
            # Daily stand-in for sign-off -- clears the latch only,
            # leaving the leash's pull-duration clock running (module
            # docstring, point 7; agents/gracie.py module docstring,
            # point 11).
            gracie.clear_fault(reset_leash_timer=False)
        last_day = day

        level_hit_now = v > rule.level_high or v < rule.level_low

        gracie.process_readings({channel: v}, timestamp=t.timestamp())

        new_latched = gracie._last_readings[channel]["severity"]
        jump_now = gracie._last_readings[channel]["jump"]
        new_aggregate = gracie.health_state

        if new_latched != prior_latched and new_latched in ("WARNING", "FAULT"):
            (level_events if level_hit_now else leash_events).append((t, new_latched))
        prior_latched = new_latched

        if jump_now:
            jump_events.append((t, "WARNING"))

        if new_aggregate != prior_aggregate and new_aggregate in ("WARNING", "FAULT"):
            any_events.append((t, new_aggregate))
        prior_aggregate = new_aggregate

    # Communication Gap isn't scored as a category either -- it isn't
    # a reading at all, so there's nothing for GRACIE to have caught
    # or missed.
    test_labels = [(cat, s, e) for cat, s, e in labels if e >= cutoff and cat != "Communication Gap"]
    cause_events = {"level": level_events, "jump": jump_events, "leash": leash_events, "any": any_events}

    def severities_in_window(events, start, end):
        lo, hi = start.timestamp() - GRACE_SECONDS, end.timestamp() + GRACE_SECONDS
        return [sev for t, sev in events if lo <= t.timestamp() <= hi]

    scorecard = {}
    for category, start, end in test_labels:
        bucket = scorecard.setdefault(category, {
            "total": 0,
            **{cause: {"caught_logged": 0, "caught_flagged": 0} for cause in cause_events}
        })
        bucket["total"] += 1
        for cause, events in cause_events.items():
            hits = severities_in_window(events, start, end)
            if hits:
                bucket[cause]["caught_logged"] += 1
            if "FAULT" in hits:
                bucket[cause]["caught_flagged"] += 1

    false_counts = {cause: {"false_logged": 0, "false_flagged": 0} for cause in cause_events}
    for cause, events in cause_events.items():
        for t, sev in events:
            if label_at(t, test_labels) is not None:
                continue  # inside a labelled window -- not a false positive
            false_counts[cause]["false_flagged" if sev == "FAULT" else "false_logged"] += 1

    return {
        "rule": rule_values,
        "scorecard": scorecard,
        "false_counts": false_counts,
        "n_level_events": len(level_events),
        "n_jump_events": len(jump_events),
        "n_leash_events": len(leash_events),
    }


# --- checkpointed per-channel driver ------------------------------------------

def run_mission(mission_zip_filename):
    path = os.path.join(DATA_DIR, mission_zip_filename)
    prefix = mission_zip_filename.replace(".zip", "")
    os.makedirs(RESULTS_DIR, exist_ok=True)
    results_path = os.path.join(RESULTS_DIR, f"{prefix}.json")

    results = {}
    if os.path.exists(results_path):
        with open(results_path) as f:
            results = json.load(f)

    channels_rows = load_channels_csv(path, prefix)
    anomaly_types = load_anomaly_types(path, prefix)
    selected = select_channels(channels_rows)
    start, end = MISSION_SPANS[mission_zip_filename]
    cutoff = start + (end - start) * CUTOFF_FRACTION

    print(f"=== {mission_zip_filename} ===")
    print(f"Selected channels (fixed, seed={SELECTION_SEED}): {selected}")
    print(f"Cutoff date ({CUTOFF_FRACTION:.0%} of mission span): {cutoff}")

    for channel in selected:
        if channel in results:
            print(f"{channel}: already done, skipping (resume).")
            continue

        t0 = time.time()
        try:
            timestamps, values = load_channel_series(path, prefix, channel)
            labels = load_labels_for_channel(path, prefix, anomaly_types, channel)
            rules = derive_rules(timestamps, values, labels, cutoff)

            channel_result = {"n_samples": len(values)}
            for setting_name, rule_values in rules.items():
                channel_result[setting_name] = score_test_period(
                    channel, rule_values, timestamps, values, labels, cutoff
                )
            channel_result["elapsed_seconds"] = time.time() - t0
        except Exception as exc:
            # One bad channel must never take down an unattended,
            # overnight, multi-hour run -- logged and skipped, not
            # silently dropped: it's recorded in the results file so
            # it's visible on review, with a different shape
            # ("error" key) from a real scorecard.
            channel_result = {"error": repr(exc), "elapsed_seconds": time.time() - t0}
            print(f"{channel}: FAILED after {channel_result['elapsed_seconds']:.1f}s -- {exc!r}")

        results[channel] = channel_result
        with open(results_path, "w") as f:
            json.dump(results, f, default=str, indent=2)
        if "error" not in channel_result:
            print(f"{channel}: done in {channel_result['elapsed_seconds']:.1f}s "
                  f"({channel_result['n_samples']} samples) -- checkpointed.")

    return results


def main():
    print("ESA-ADB -- Missions 1 and 2 only. FIRST TEST AGAINST REAL SPACECRAFT DATA. NOT A VALIDATION.")
    print("Cite: De Canio, Kotowski, Haskamp et al. (2024), https://doi.org/10.5281/zenodo.12528696, CC BY 3.0 IGO.")
    for mission in ["ESA-Mission1.zip", "ESA-Mission2.zip"]:
        run_mission(mission)


if __name__ == "__main__":
    main()
