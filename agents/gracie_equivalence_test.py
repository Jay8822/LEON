# agents/gracie_equivalence_test.py
# Added 2026-10-25 — Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Proves the rewritten GracieAgent's INCREMENTAL jump/leash trackers
give the same answers as the BATCH scripts they were rewritten from
(run_opssat_ad_test.py, simulated_tests/leash_drift/) -- required by
Jay before trusting the rewrite: "if anything doesn't match, stop,
don't paper over it, and explain the difference."

Two checks:

1. Leash timing, against simulated_tests/leash_drift/: the same 5
   seeds, both channels, same derived slope limit and durations. The
   batch's find_pull_episodes() has no latching concept at all --
   every maximal run past the limit is its own independent episode.
   GracieAgent's PUBLIC severity does latch (point 3 of gracie.py's
   module docstring), so this test compares against the UNDERLYING,
   per-pull edge-detectors (_ChannelState.soft_active/hard_active)
   instead of the gated latched_severity -- see _ChannelState's
   docstring for exactly why those are kept separate. Comparing the
   edge-detectors is the fair, apples-to-apples check: same detection
   maths, latching is a GracieAgent-only layer on top that the batch
   scripts never had an opinion on.

2. Level and jump, against a slice of real_data_tests/opssat_ad/'s
   test fragments: a fresh GracieAgent per fragment (mirroring the
   batch's per-fragment independence), same derived STRICT-setting
   thresholds, fed one sample at a time.

Run from the repo root, after both:
    python -m real_data_tests.opssat_ad.download_opssat_ad
    (simulated_tests/leash_drift needs no download of its own -- it
    reads the same OPSSAT-AD file as its noise source)

    python -m agents.gracie_equivalence_test
"""

from agents.gracie import GracieAgent
from agents.gracie_rulebook import ChannelRule
from core.bus import EventBus

from real_data_tests.opssat_ad.run_opssat_ad_test import (
    Fragment,
    SETTINGS,
    derive_jump_limits,
    derive_thresholds,
    flagged,
    jump_flagged,
    load_fragments,
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
from simulated_tests.leash_drift.run_leash_drift_test import SEEDS, find_pull_episodes

# A wide-open rule for whichever of the three senses isn't the one
# being checked in a given slice, so it can never fire and confound
# the comparison -- same "disable what you're not testing" fixture
# pattern as agents/gracie_test.py's DRIFT_RULE.
_HARMLESS_HIGH = 1e12
_HARMLESS_LOW = -1e12
OPS_SAT_FRAGMENT_SLICE = 40  # first N test fragments -- enough to be meaningful, fast to run


def seconds_from_start(timestamps):
    t0 = timestamps[0]
    return [(t - t0).total_seconds() for t in timestamps]


def test_leash_timing_matches_batch_for_every_seed_and_channel():
    for channel in CHANNELS:
        delta_pool = load_real_delta_pool(channel)
        limit = derive_limit_for_channel(channel, delta_pool)

        for seed in SEEDS:
            timestamps, values, _events = build_scenario(channel, delta_pool, limit, seed)
            seconds = seconds_from_start(timestamps)

            # --- batch ---
            frag = Fragment(segment_id="sim", channel=channel, anomalous=False, is_train=False)
            frag.values = values
            frag.timestamps = timestamps
            slopes = frag._windowed_slopes()
            batch_soft = sorted((t - timestamps[0]).total_seconds() for t, _ in find_pull_episodes(
                slopes, limit, LEASH_SOFT_DURATION_SECONDS))
            batch_hard = sorted((t - timestamps[0]).total_seconds() for t, _ in find_pull_episodes(
                slopes, limit, LEASH_HARD_DURATION_SECONDS))

            # --- incremental GracieAgent ---
            rule = ChannelRule(
                name=channel, units="u",
                level_high=_HARMLESS_HIGH, level_low=_HARMLESS_LOW,
                jump_limit=_HARMLESS_HIGH,
                leash_window_seconds=LEASH_WINDOW_SECONDS, leash_slope_limit=limit,
                leash_soft_duration_seconds=LEASH_SOFT_DURATION_SECONDS,
                leash_hard_duration_seconds=LEASH_HARD_DURATION_SECONDS,
            )
            bus = EventBus()
            gracie = GracieAgent(bus, {channel: rule})
            state = gracie._states[channel]

            gracie_soft, gracie_hard = [], []
            prev_soft, prev_hard = False, False
            for t, v in zip(seconds, values):
                gracie.process_readings({channel: v}, timestamp=t)
                if state.soft_active and not prev_soft:
                    gracie_soft.append(t)
                if state.hard_active and not prev_hard:
                    gracie_hard.append(t)
                prev_soft, prev_hard = state.soft_active, state.hard_active

            assert gracie_soft == batch_soft, (
                f"{channel} seed={seed}: SOFT timing mismatch -- "
                f"batch={batch_soft} gracie={gracie_soft}"
            )
            assert gracie_hard == batch_hard, (
                f"{channel} seed={seed}: HARD timing mismatch -- "
                f"batch={batch_hard} gracie={gracie_hard}"
            )
    print(f"  ok: leash timing matches the batch scripts exactly, "
          f"{len(CHANNELS)} channels x {len(SEEDS)} seeds, every soft and hard transition")


def test_level_and_jump_match_batch_for_a_slice_of_ops_sat_fragments():
    fragments = load_fragments()
    train_fragments = [f for f in fragments if f.is_train]
    test_fragments = [f for f in fragments if not f.is_train][:OPS_SAT_FRAGMENT_SLICE]

    high_pct, low_pct = SETTINGS["STRICT (95th/5th percentile)"]
    thresholds = derive_thresholds(train_fragments, high_pct, low_pct)
    jump_limits = derive_jump_limits(train_fragments, high_pct)

    checked = 0
    for frag in test_fragments:
        channel = frag.channel
        if channel not in thresholds or channel not in jump_limits:
            continue  # no derived rule for this channel -- nothing to compare

        batch_level = flagged(frag, thresholds)
        batch_jump = jump_flagged(frag, jump_limits)

        rule = ChannelRule(
            name=channel, units="u",
            level_high=thresholds[channel]["high"], level_low=thresholds[channel]["low"],
            jump_limit=jump_limits[channel]["limit"],
            leash_window_seconds=1.0, leash_slope_limit=_HARMLESS_HIGH,
            leash_soft_duration_seconds=_HARMLESS_HIGH, leash_hard_duration_seconds=_HARMLESS_HIGH,
        )
        bus = EventBus()
        gracie = GracieAgent(bus, {channel: rule})

        seconds = seconds_from_start(frag.timestamps)
        any_jump = False
        for t, v in zip(seconds, frag.values):
            gracie.process_readings({channel: v}, timestamp=t)
            any_jump = any_jump or gracie._last_readings[channel]["jump"]
        gracie_level = gracie._states[channel].latched_severity == "FAULT"

        assert gracie_level == batch_level, (
            f"{channel} segment={frag.segment_id}: LEVEL mismatch -- "
            f"batch={batch_level} gracie={gracie_level}"
        )
        assert any_jump == batch_jump, (
            f"{channel} segment={frag.segment_id}: JUMP mismatch -- "
            f"batch={batch_jump} gracie={any_jump}"
        )
        checked += 1

    assert checked > 0, "no fragments were actually compared -- slice or thresholds are wrong"
    print(f"  ok: level and jump match the batch script exactly, "
          f"across {checked} real OPSSAT-AD test fragments")


def main():
    tests = [
        test_leash_timing_matches_batch_for_every_seed_and_channel,
        test_level_and_jump_match_batch_for_a_slice_of_ops_sat_fragments,
    ]
    for test in tests:
        test()
    print("All GRACIE batch/incremental equivalence checks passed.")


if __name__ == "__main__":
    main()
