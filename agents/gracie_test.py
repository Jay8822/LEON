# agents/gracie_test.py
# Rewritten 2026-10-25 — any-sensor upgrade. Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Checks for the rewritten GracieAgent (any-sensor, rule-book-driven,
three independent senses per channel). Replaces the old test, which
was built entirely around the temp_c-AND-radiation scaffolding that's
now gone.

The rule book below is a test fixture, not real hardware data —
clearly arbitrary numbers, chosen to make the three senses easy to
exercise with a handful of steps, never claimed as real spacecraft
thresholds. Same "no invented numbers" discipline as
agents/escalation_orchestrator_test.py's fixture rule sets.

Run from the repo root:

    python -m agents.gracie_test
"""

from agents.gracie import GracieAgent
from agents.gracie_rulebook import ChannelRule
from core.bus import EventBus

# Fixture rule book -- arbitrary, round numbers chosen for easy
# arithmetic in these tests, not real thresholds.
TEMP_RULE = ChannelRule(
    name="temp_c", units="C",
    level_high=55.0, level_low=-20.0,
    jump_limit=5.0,
    leash_window_seconds=10.0, leash_slope_limit=1.0,
    leash_soft_duration_seconds=20.0, leash_hard_duration_seconds=40.0,
)
RAD_RULE = ChannelRule(
    name="radiation", units="rad",
    level_high=40.0, level_low=0.0,
    jump_limit=3.0,
    leash_window_seconds=10.0, leash_slope_limit=0.5,
    leash_soft_duration_seconds=20.0, leash_hard_duration_seconds=40.0,
)
# A separate fixture channel for the leash tests specifically: level
# bounds set far outside anything the ramp below ever reaches, so a
# long, deliberate drift doesn't incidentally also trip the level
# check and confound what's being tested. jump_limit is likewise set
# well above the ramp's own step size for the same reason.
DRIFT_RULE = ChannelRule(
    name="drift_channel", units="u",
    level_high=1_000_000.0, level_low=-1_000_000.0,
    jump_limit=1_000.0,
    leash_window_seconds=10.0, leash_slope_limit=1.0,
    leash_soft_duration_seconds=20.0, leash_hard_duration_seconds=40.0,
)

# A second drift-style channel, with REACHABLE level bounds (unlike
# DRIFT_RULE's, set deliberately out of range), for the "settling soft
# pull on a channel already in an active level FAULT" case.
COMBO_RULE = ChannelRule(
    name="combo_channel", units="u",
    level_high=200.0, level_low=-200.0,
    jump_limit=1_000.0,
    leash_window_seconds=10.0, leash_slope_limit=1.0,
    leash_soft_duration_seconds=20.0, leash_hard_duration_seconds=40.0,
)

# Two channels for the LINKED-channel exception: A's own level bounds
# are unreachable (same convention as DRIFT_RULE), but A is linked to
# B via linked_channels, so B's level FAULT should hold A's settling
# leash pull latched too, same as if it were A's own fault.
LINKED_A_RULE = ChannelRule(
    name="linked_a", units="u",
    level_high=1_000_000.0, level_low=-1_000_000.0,
    jump_limit=1_000.0,
    leash_window_seconds=10.0, leash_slope_limit=1.0,
    leash_soft_duration_seconds=20.0, leash_hard_duration_seconds=40.0,
    linked_channels=("linked_b",),
)
LINKED_B_RULE = ChannelRule(
    name="linked_b", units="u",
    level_high=200.0, level_low=-200.0,
    jump_limit=1_000.0,
    leash_window_seconds=10.0, leash_slope_limit=1.0,
    leash_soft_duration_seconds=20.0, leash_hard_duration_seconds=40.0,
)

RULE_BOOK = {
    "temp_c": TEMP_RULE, "radiation": RAD_RULE,
    "drift_channel": DRIFT_RULE, "combo_channel": COMBO_RULE,
    "linked_a": LINKED_A_RULE, "linked_b": LINKED_B_RULE,
}


def make_gracie():
    bus = EventBus()
    reports = []
    chester_announcements = []
    bus.subscribe("telemetry/health", reports.append)
    bus.subscribe("chester/watch", chester_announcements.append)
    gracie = GracieAgent(bus, RULE_BOOK)
    return gracie, reports, chester_announcements


def test_level_is_independent_per_channel():
    gracie, _, _ = make_gracie()
    gracie.process_readings({"temp_c": 30, "radiation": 10}, timestamp=0)
    assert gracie.health_state == "NOMINAL"

    # Only temp_c crosses -- radiation must not be dragged along with it.
    gracie.process_readings({"temp_c": 56, "radiation": 10}, timestamp=1)
    assert gracie.health_state == "FAULT"
    assert gracie._last_readings["temp_c"]["severity"] == "FAULT"
    assert gracie._last_readings["radiation"]["severity"] == "NOMINAL"

    # Now radiation crosses too, independently.
    gracie.process_readings({"temp_c": 30, "radiation": 45}, timestamp=2)
    assert gracie._last_readings["temp_c"]["severity"] == "FAULT"  # still latched
    assert gracie._last_readings["radiation"]["severity"] == "FAULT"
    assert gracie.health_state == "FAULT"
    print("  ok: level crossings are independent per channel, no AND condition")


def test_clear_fault_per_channel_and_all():
    gracie, _, _ = make_gracie()
    gracie.process_readings({"temp_c": 56, "radiation": 45}, timestamp=0)
    assert gracie.health_state == "FAULT"

    gracie.clear_fault("temp_c")
    assert gracie._last_readings["temp_c"]["severity"] == "NOMINAL"
    assert gracie._last_readings["radiation"]["severity"] == "FAULT"
    assert gracie.health_state == "FAULT"  # radiation still latched

    gracie.clear_fault()  # no argument -- clears every channel
    assert gracie._last_readings["temp_c"]["severity"] == "NOMINAL"
    assert gracie._last_readings["radiation"]["severity"] == "NOMINAL"
    assert gracie.health_state == "NOMINAL"
    print("  ok: clear_fault(channel) clears just that channel; clear_fault() clears all")


def test_jump_is_momentary_not_latched():
    gracie, _, _ = make_gracie()
    gracie.process_readings({"radiation": 0}, timestamp=0)
    assert gracie.health_state == "NOMINAL"

    gracie.process_readings({"radiation": 10}, timestamp=1)  # rate=10/s > jump_limit=3/s
    assert gracie._last_readings["radiation"]["jump"] is True
    assert gracie.health_state == "WARNING"

    gracie.process_readings({"radiation": 10}, timestamp=2)  # no change -- no new jump
    assert gracie._last_readings["radiation"]["jump"] is False
    assert gracie.health_state == "NOMINAL", "a jump must not latch -- it's momentary"
    print("  ok: jump fires on its own cycle only, never latches")


def test_leash_soft_then_hard_by_duration():
    gracie, _, _ = make_gracie()
    # A steady ramp of 2 units/s -- comfortably over leash_slope_limit
    # (1.0/s). window=10s, soft=20s, hard=40s. The pull begins once the
    # window first fills (t=10), so soft is expected at t=30 (10+20),
    # hard at t=50 (10+40).
    for t in range(0, 51):
        gracie.process_readings({"drift_channel": 2.0 * t}, timestamp=float(t))
        severity = gracie._last_readings["drift_channel"]["severity"]
        if t < 30:
            assert severity == "NOMINAL", (t, severity)
        elif t < 50:
            assert severity == "WARNING", (t, severity)
        else:
            assert severity == "FAULT", (t, severity)
    print("  ok: leash reaches soft at its soft duration, hard at its (longer) hard duration")


def test_leash_settles_back_before_hard_clears_and_announces_for_chester():
    gracie, _, chester = make_gracie()
    t = 0
    # Ramp up past soft (reached at t=30, same as the test above).
    for t in range(0, 31):
        gracie.process_readings({"drift_channel": 2.0 * t}, timestamp=float(t))
    assert gracie._last_readings["drift_channel"]["severity"] == "WARNING"
    assert chester == []

    # Now hold flat -- the windowed slope decays toward 0 well before
    # hard's duration (40s) would otherwise be reached, so the pull
    # settles back on its own.
    flat_value = 2.0 * t
    for extra in range(1, 15):
        gracie.process_readings({"drift_channel": flat_value}, timestamp=float(t + extra))

    assert gracie._last_readings["drift_channel"]["severity"] == "NOMINAL", \
        "a soft pull that settles back must clear itself, not stay stuck at WARNING"
    assert len(chester) == 1, chester
    assert chester[0]["kind"] == "leash_settled"
    assert chester[0]["channel"] == "drift_channel"
    assert "readings" in chester[0]
    print("  ok: a settling soft pull clears to NOMINAL and announces once on chester/watch")


def test_leash_settles_back_stays_with_an_active_level_fault():
    gracie, _, chester = make_gracie()
    t = 0
    # combo_channel starts already past its level FAULT (level_high=200)
    # and keeps climbing at the same 2 units/s ramp, so it independently
    # builds a leash pull on top of an already-latched level fault.
    for t in range(0, 31):
        gracie.process_readings({"combo_channel": 250.0 + 2.0 * t}, timestamp=float(t))
    assert gracie._last_readings["combo_channel"]["severity"] == "FAULT"  # from LEVEL, not leash

    # Hold flat -- the leash pull settles, same as the test above, but
    # the level fault is still independently active throughout.
    flat_value = 250.0 + 2.0 * t
    for extra in range(1, 15):
        gracie.process_readings({"combo_channel": flat_value}, timestamp=float(t + extra))

    assert gracie._last_readings["combo_channel"]["severity"] == "FAULT", \
        "a settling leash pull must not clear a channel that's independently still FAULT"
    assert chester == [], "no hand-off to CHESTER while the channel is part of an active major fault"
    print("  ok: a settling soft pull stays with an already-active level FAULT, not handed off")


def test_leash_settles_back_stays_with_a_linked_channels_active_fault():
    gracie, _, chester = make_gracie()
    # B gets its own level FAULT first -- A is linked to B, not the
    # other way round, and A's own level bounds are unreachable, so
    # any latching on A can only come from its own leash pull or from
    # B via linked_channels.
    gracie.process_readings({"linked_b": 300.0}, timestamp=-1)
    assert gracie._last_readings["linked_b"]["severity"] == "FAULT"

    t = 0
    # A independently builds a leash pull past soft, same ramp as the
    # other leash tests, with B's fault already active throughout.
    for t in range(0, 31):
        gracie.process_readings({"linked_a": 2.0 * t}, timestamp=float(t))
    assert gracie._last_readings["linked_a"]["severity"] == "WARNING"

    # Hold flat -- A's pull settles back on its own.
    flat_value = 2.0 * t
    for extra in range(1, 15):
        gracie.process_readings({"linked_a": flat_value}, timestamp=float(t + extra))

    assert gracie._last_readings["linked_a"]["severity"] == "WARNING", \
        "A must stay latched while B, which A is linked to, is still an active major fault"
    assert chester == [], "no hand-off to CHESTER while a linked channel has an active major fault"
    print("  ok: a settling soft pull stays latched when linked to a DIFFERENT channel's active fault")


def test_report_carries_actual_readings():
    gracie, reports, _ = make_gracie()
    gracie.process_readings({"temp_c": 30, "radiation": 10}, timestamp=0)
    last = reports[-1]
    assert last["system_health"] == "NOMINAL"
    assert last["source"] == "GRACIE"
    assert last["readings"]["temp_c"]["value"] == 30
    assert last["readings"]["temp_c"]["units"] == "C"
    assert last["readings"]["radiation"]["value"] == 10

    # A diagnostics-triggered report (no new sample) still carries the
    # last known readings -- SPEC.md's open item, satisfied every time.
    gracie.on_command({"command": "run_diagnostics"})
    assert reports[-1]["readings"]["temp_c"]["value"] == 30
    print("  ok: every report carries real per-channel readings, including diagnostics-triggered ones")


def test_unrecognized_channel_is_ignored_not_guessed_at():
    gracie, _, _ = make_gracie()
    gracie.process_readings({"temp_c": 30, "mystery_channel": 999}, timestamp=0)
    assert "mystery_channel" not in gracie._last_readings
    assert gracie.health_state == "NOMINAL"
    print("  ok: a channel with no rule-book entry is logged and ignored, not guessed at")


def main():
    tests = [
        test_level_is_independent_per_channel,
        test_clear_fault_per_channel_and_all,
        test_jump_is_momentary_not_latched,
        test_leash_soft_then_hard_by_duration,
        test_leash_settles_back_before_hard_clears_and_announces_for_chester,
        test_leash_settles_back_stays_with_an_active_level_fault,
        test_leash_settles_back_stays_with_a_linked_channels_active_fault,
        test_report_carries_actual_readings,
        test_unrecognized_channel_is_ignored_not_guessed_at,
    ]
    for test in tests:
        test()
    print("All GRACIE any-sensor checks passed.")


if __name__ == "__main__":
    main()
