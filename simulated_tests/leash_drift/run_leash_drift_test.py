# simulated_tests/leash_drift/run_leash_drift_test.py
# Added 2026-10-24 — Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""SIMULATED leash (drift-sense) sensitivity test. Not real spacecraft
data -- a controlled-conditions check of the mechanism itself, where
the truth is known exactly, like reviewing CCTV footage at high speed
with incidents planted on purpose. Every result below is labelled
SIMULATED. Never mixed into real_data_tests/opssat_ad/'s scorecards.

Built because OPS-SAT's own fragments turned out too short/spike-
shaped to exercise sustained drift (real_data_tests/opssat_ad's
leash scorecard registers zero pulls anywhere). This test answers a
different question: given a planted drift of a known duration, does
the leash mechanism (as built for that test) actually catch it at the
right strength (soft/hard), and how fast? It says nothing about
whether real spacecraft drift looks like these planted shapes --
ESA-ADB, later, is the real long-duration test.

Updated 2026-10-24: the leash was redefined from two slope-based
limits (soft/hard) to one slope limit plus two durations -- soft and
hard came out almost identical as slopes on real data, so that
version couldn't show them working separately. This version plants
drifts of different DURATIONS at the same comfortable slope margin
instead, to test the soft/hard duration distinction directly. See
generate_leash_drift.py's module docstring for exactly how.

Run from the repo root, after real_data_tests/opssat_ad's download
script (the noise source):

    python -m simulated_tests.leash_drift.run_leash_drift_test
"""

from real_data_tests.opssat_ad.run_opssat_ad_test import (
    Fragment,
    LEASH_WINDOW_SECONDS,
    LEASH_SOFT_DURATION_SECONDS,
    LEASH_HARD_DURATION_SECONDS,
)

from simulated_tests.leash_drift.generate_leash_drift import (
    CHANNELS,
    build_scenario,
    derive_limit_for_channel,
    load_real_delta_pool,
)

SEEDS = [1, 2, 3, 4, 5]
# Grace period after a planted event's nominal end, to allow for the
# windowed slope's own smoothing lag -- a detection just after the
# ramp stops is still attributable to that event, not a false pull.
GRACE_SECONDS = LEASH_WINDOW_SECONDS


def find_pull_episodes(windowed_slopes, limit, duration_seconds):
    """Every maximal continuous run where |slope| > limit for at least
    `duration_seconds`. Returns (detected_at, ended_at) pairs --
    detected_at is the sample time the sustained condition first
    becomes true (the moment the leash would register it); ended_at is
    when it first drops back at/under the limit."""
    episodes = []
    run_start = None
    active = False
    for t, s in windowed_slopes:
        if abs(s) > limit:
            if run_start is None:
                run_start = t
            if not active and (t - run_start).total_seconds() >= duration_seconds:
                active = True
                episodes.append([t, None])
        else:
            if active:
                episodes[-1][1] = t
            run_start = None
            active = False
    if active:
        episodes[-1][1] = windowed_slopes[-1][0]
    return [(s, e) for s, e in episodes]


def score_scenario(timestamps, values, events, limit):
    frag = Fragment(segment_id="sim", channel="sim", anomalous=False, is_train=False)
    frag.values = values
    frag.timestamps = timestamps
    slopes = frag._windowed_slopes()

    soft_episodes = find_pull_episodes(slopes, limit, LEASH_SOFT_DURATION_SECONDS)
    hard_episodes = find_pull_episodes(slopes, limit, LEASH_HARD_DURATION_SECONDS)
    t0 = timestamps[0]

    def seconds_of(ts):
        return (ts - t0).total_seconds()

    event_results = []
    for event in events:
        window = (event["start_s"], event["end_s"] + GRACE_SECONDS)
        soft_hit = next((s for s, _ in soft_episodes if window[0] <= seconds_of(s) <= window[1]), None)
        hard_hit = next((s for s, _ in hard_episodes if window[0] <= seconds_of(s) <= window[1]), None)
        detected_at = min(t for t in [soft_hit, hard_hit] if t is not None) if (soft_hit or hard_hit) else None
        event_results.append({
            **event,
            "soft_caught": soft_hit is not None,
            "hard_caught": hard_hit is not None,
            "soft_delay_s": seconds_of(soft_hit) - event["start_s"] if soft_hit else None,
            "hard_delay_s": seconds_of(hard_hit) - event["start_s"] if hard_hit else None,
        })

    def is_false_pull(detected_at):
        s = seconds_of(detected_at)
        return not any(e["start_s"] <= s <= e["end_s"] + GRACE_SECONDS for e in events)

    false_pulls_soft = sum(1 for s, _ in soft_episodes if is_false_pull(s))
    false_pulls_hard = sum(1 for s, _ in hard_episodes if is_false_pull(s))

    return event_results, false_pulls_soft, false_pulls_hard


def main():
    print("SIMULATED leash (drift-sense) sensitivity test -- not real spacecraft data.")
    print(f"Window={LEASH_WINDOW_SECONDS:.0f}s, one slope limit per channel, "
          f"soft_duration={LEASH_SOFT_DURATION_SECONDS:.0f}s, hard_duration={LEASH_HARD_DURATION_SECONDS:.0f}s "
          f"(same values as real_data_tests/opssat_ad). Seeds: {SEEDS}.\n")

    for channel in CHANNELS:
        delta_pool = load_real_delta_pool(channel)
        limit = derive_limit_for_channel(channel, delta_pool)
        print(f"=== {channel} === SIMULATED. slope_limit={limit:.6g}/s "
              f"(derived from {len(delta_pool)} real nominal training deltas, seed 0 for derivation)")

        total_false_soft = 0
        total_false_hard = 0
        returns_logged_count = 0
        mismatches = []

        for seed in SEEDS:
            timestamps, values, events = build_scenario(channel, delta_pool, limit, seed)
            results, fp_soft, fp_hard = score_scenario(timestamps, values, events, limit)
            total_false_soft += fp_soft
            total_false_hard += fp_hard

            print(f"  -- seed {seed} -- SIMULATED")
            for r in results:
                soft_delay = f"{r['soft_delay_s']:.0f}s" if r["soft_delay_s"] is not None else "n/a"
                hard_delay = f"{r['hard_delay_s']:.0f}s" if r["hard_delay_s"] is not None else "n/a"
                print(f"     {r['name']:>12}: expected soft={r['expected_soft']!s:<5} hard={r['expected_hard']!s:<5} "
                      f"| got soft={r['soft_caught']!s:<5} (delay={soft_delay}) "
                      f"hard={r['hard_caught']!s:<5} (delay={hard_delay})")
                if r["soft_caught"] != r["expected_soft"] or r["hard_caught"] != r["expected_hard"]:
                    mismatches.append((seed, r["name"]))
                if r["name"] == "returns" and (r["soft_caught"] or r["hard_caught"]):
                    returns_logged_count += 1
            print(f"     false pulls on control stretches -- SIMULATED: soft={fp_soft} hard={fp_hard}")

        print(f"  TOTAL over {len(SEEDS)} seeds -- SIMULATED:")
        print(f"    false pulls on control stretches: soft={total_false_soft} hard={total_false_hard}")
        print(f"    'returns to normal' event logged (soft or hard) in {returns_logged_count}/{len(SEEDS)} seeds")
        if mismatches:
            print(f"    MISMATCHES vs. expectation: {mismatches}")
        else:
            print("    every event matched its expectation (soft/hard/neither) in every seed")
        print()


if __name__ == "__main__":
    main()
