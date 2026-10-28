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
    stuck_window_seconds=10.0, min_normal_noise=0.0,  # Stillness not exercised by this rule
    level_fault_class=None, jump_fault_class=None, leash_soft_fault_class=None,
    leash_hard_fault_class=None, stillness_fault_class=None,  # Item C: not stated this round
)
RAD_RULE = ChannelRule(
    name="radiation", units="rad",
    level_high=40.0, level_low=0.0,
    jump_limit=3.0,
    leash_window_seconds=10.0, leash_slope_limit=0.5,
    leash_soft_duration_seconds=20.0, leash_hard_duration_seconds=40.0,
    stuck_window_seconds=10.0, min_normal_noise=0.0,  # Stillness not exercised by this rule
    level_fault_class=None, jump_fault_class=None, leash_soft_fault_class=None,
    leash_hard_fault_class=None, stillness_fault_class=None,  # Item C: not stated this round
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
    stuck_window_seconds=10.0, min_normal_noise=0.0,  # Stillness not exercised by this rule
    level_fault_class=None, jump_fault_class=None, leash_soft_fault_class=None,
    leash_hard_fault_class=None, stillness_fault_class=None,  # Item C: not stated this round
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
    stuck_window_seconds=10.0, min_normal_noise=0.0,  # Stillness not exercised by this rule
    level_fault_class=None, jump_fault_class=None, leash_soft_fault_class=None,
    leash_hard_fault_class=None, stillness_fault_class=None,  # Item C: not stated this round
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
    stuck_window_seconds=10.0, min_normal_noise=0.0,  # Stillness not exercised by this rule
    level_fault_class=None, jump_fault_class=None, leash_soft_fault_class=None,
    leash_hard_fault_class=None, stillness_fault_class=None,  # Item C: not stated this round
    linked_channels=("linked_b",),
)
LINKED_B_RULE = ChannelRule(
    name="linked_b", units="u",
    level_high=200.0, level_low=-200.0,
    jump_limit=1_000.0,
    leash_window_seconds=10.0, leash_slope_limit=1.0,
    leash_soft_duration_seconds=20.0, leash_hard_duration_seconds=40.0,
    stuck_window_seconds=10.0, min_normal_noise=0.0,  # Stillness not exercised by this rule
    level_fault_class=None, jump_fault_class=None, leash_soft_fault_class=None,
    leash_hard_fault_class=None, stillness_fault_class=None,  # Item C: not stated this round
)

# A channel with a REAL Stillness limit -- level/jump/leash bounds set
# unreachable (same convention as DRIFT_RULE) so only Stillness can
# fire, isolating what's being tested.
STUCK_RULE = ChannelRule(
    name="stuck_channel", units="u",
    level_high=1_000_000.0, level_low=-1_000_000.0,
    jump_limit=1_000_000.0,
    leash_window_seconds=10.0, leash_slope_limit=1_000_000.0,
    leash_soft_duration_seconds=1_000_000.0, leash_hard_duration_seconds=1_000_000.0,
    stuck_window_seconds=5.0, min_normal_noise=2.0,
    level_fault_class=None, jump_fault_class=None, leash_soft_fault_class=None,
    leash_hard_fault_class=None, stillness_fault_class=None,  # Item C: not stated this round
)
# Same limits, but explicitly exempted -- a sensor the blueprint says
# legitimately holds steady (SPEC.md Stillness bullet).
STEADY_RULE = ChannelRule(
    name="steady_channel", units="u",
    level_high=1_000_000.0, level_low=-1_000_000.0,
    jump_limit=1_000_000.0,
    leash_window_seconds=10.0, leash_slope_limit=1_000_000.0,
    leash_soft_duration_seconds=1_000_000.0, leash_hard_duration_seconds=1_000_000.0,
    stuck_window_seconds=5.0, min_normal_noise=2.0,
    level_fault_class=None, jump_fault_class=None, leash_soft_fault_class=None,
    leash_hard_fault_class=None, stillness_fault_class=None,  # Item C: not stated this round
    allow_steady=True,
)

RULE_BOOK = {
    "temp_c": TEMP_RULE, "radiation": RAD_RULE,
    "drift_channel": DRIFT_RULE, "combo_channel": COMBO_RULE,
    "linked_a": LINKED_A_RULE, "linked_b": LINKED_B_RULE,
    "stuck_channel": STUCK_RULE, "steady_channel": STEADY_RULE,
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


def test_clear_fault_default_resets_the_leash_timer():
    gracie, _, _ = make_gracie()
    for t in range(0, 31):
        gracie.process_readings({"drift_channel": 2.0 * t}, timestamp=float(t))
    assert gracie._last_readings["drift_channel"]["severity"] == "WARNING"

    gracie.clear_fault("drift_channel")  # reset_leash_timer defaults to True
    assert gracie._last_readings["drift_channel"]["severity"] == "NOMINAL"

    # The pull never stopped (still ramping at the same slope), but the
    # clock restarted fresh at t=31 (the first sample after the
    # clear) -- hard (31 + 40) is now expected at t=71, NOT anywhere
    # near the original t=50.
    for t in range(31, 50):
        gracie.process_readings({"drift_channel": 2.0 * t}, timestamp=float(t))
    assert gracie._last_readings["drift_channel"]["severity"] == "NOMINAL", \
        "the default clear_fault() resets the clock, so nothing should have re-fired yet by the old t=50"
    for t in range(50, 72):
        gracie.process_readings({"drift_channel": 2.0 * t}, timestamp=float(t))
    assert gracie._last_readings["drift_channel"]["severity"] == "FAULT", \
        "hard should now arrive ~40s after the fresh start at t=31, i.e. at t=71"
    print("  ok: clear_fault()'s default (reset_leash_timer=True) resets the leash clock, unchanged")


def test_clear_fault_can_leave_the_leash_timer_running():
    gracie, _, _ = make_gracie()
    for t in range(0, 31):
        gracie.process_readings({"drift_channel": 2.0 * t}, timestamp=float(t))
    assert gracie._last_readings["drift_channel"]["severity"] == "WARNING"

    gracie.clear_fault("drift_channel", reset_leash_timer=False)
    assert gracie._last_readings["drift_channel"]["severity"] == "NOMINAL"

    # The pull keeps going, uninterrupted, at the same slope. Because
    # the clock was NOT reset, hard still arrives at the ORIGINAL t=50
    # (10 + 40), not 40s after the clear.
    for t in range(31, 50):
        gracie.process_readings({"drift_channel": 2.0 * t}, timestamp=float(t))
        assert gracie._last_readings["drift_channel"]["severity"] == "NOMINAL", (t,)
    gracie.process_readings({"drift_channel": 2.0 * 50}, timestamp=50.0)
    assert gracie._last_readings["drift_channel"]["severity"] == "FAULT", \
        "hard must still arrive at the original t=50 -- the clock kept running through the clear"
    print("  ok: clear_fault(reset_leash_timer=False) clears the latch but leaves the leash clock running")


def test_leash_settles_back_before_hard_clears_and_announces_for_chester():
    gracie, _, chester = make_gracie()
    t = 0
    # Ramp up past soft (reached at t=30, same as the test above).
    for t in range(0, 31):
        gracie.process_readings({"drift_channel": 2.0 * t}, timestamp=float(t))
    assert gracie._last_readings["drift_channel"]["severity"] == "WARNING"
    # Entering WARNING is announced the moment it happens, not held back.
    assert [e["kind"] for e in chester] == ["warning_entered"], chester

    # Now hold flat -- the windowed slope decays toward 0 well before
    # hard's duration (40s) would otherwise be reached, so the pull
    # settles back on its own.
    flat_value = 2.0 * t
    for extra in range(1, 15):
        gracie.process_readings({"drift_channel": flat_value}, timestamp=float(t + extra))

    assert gracie._last_readings["drift_channel"]["severity"] == "NOMINAL", \
        "a soft pull that settles back must clear itself, not stay stuck at WARNING"
    # Settling announces both: the leash-specific event, and the more
    # general "left WARNING" one -- same settling moment, two kinds.
    kinds = [e["kind"] for e in chester]
    assert kinds == ["warning_entered", "leash_settled", "warning_left"], kinds
    for e in chester:
        assert e["channel"] == "drift_channel"
        assert "readings" in e
    print("  ok: entering/leaving WARNING and the leash settling are each announced once")


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

    # A's own entering-WARNING is announced as usual; only the settle
    # (leaving WARNING) is held back by B's active fault.
    assert [e["kind"] for e in chester] == ["warning_entered"], chester
    assert gracie._last_readings["linked_a"]["severity"] == "WARNING", \
        "A must stay latched while B, which A is linked to, is still an active major fault"
    # No SECOND announcement from the settle -- still just the one
    # "warning_entered" from earlier; no "leash_settled"/"warning_left".
    assert [e["kind"] for e in chester] == ["warning_entered"], chester
    print("  ok: a settling soft pull stays latched when linked to a DIFFERENT channel's active fault, "
          "with no hand-off announcement")


def test_jump_announces_on_chester_watch():
    gracie, _, chester = make_gracie()
    gracie.process_readings({"radiation": 0}, timestamp=0)
    assert chester == []
    gracie.process_readings({"radiation": 10}, timestamp=1)  # rate=10/s > jump_limit=3/s
    assert [e["kind"] for e in chester] == ["jump"], chester
    assert chester[0]["channel"] == "radiation"
    assert chester[0]["agent"] == "GRACIE"
    gracie.process_readings({"radiation": 10}, timestamp=2)  # no change -- no new jump
    assert [e["kind"] for e in chester] == ["jump"], "no new announcement without a new jump"
    print("  ok: every jump announces once on chester/watch, not repeated without a new jump")


def test_clear_fault_announces_warning_left():
    gracie, _, chester = make_gracie()
    t = 0
    for t in range(0, 31):
        gracie.process_readings({"drift_channel": 2.0 * t}, timestamp=float(t))
    assert gracie._last_readings["drift_channel"]["severity"] == "WARNING"
    assert [e["kind"] for e in chester] == ["warning_entered"], chester

    gracie.clear_fault("drift_channel")
    assert gracie._last_readings["drift_channel"]["severity"] == "NOMINAL"
    assert [e["kind"] for e in chester] == ["warning_entered", "warning_left"], chester
    print("  ok: an explicit clear_fault() also announces leaving WARNING")


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


def test_new_crossing_while_latched_logs_but_does_not_change_anything():
    gracie, _, chester = make_gracie()
    # Small steps (well under jump_limit=5.0/s) so jump noise doesn't
    # confound what's being tested here.
    gracie.process_readings({"temp_c": 56}, timestamp=0)  # first crossing -> FAULT
    assert gracie._last_readings["temp_c"]["severity"] == "FAULT"
    assert gracie._states["temp_c"].level_crossing_active is True

    gracie.process_readings({"temp_c": 52}, timestamp=1)  # back in bounds (delta=4)
    assert gracie._last_readings["temp_c"]["severity"] == "FAULT", "still latched -- only clear_fault undoes it"
    assert gracie._states["temp_c"].level_crossing_active is False

    # A second, separate crossing while still latched FAULT from the
    # first -- severity is unaffected (already FAULT, stays FAULT), but
    # the edge-detector proves this is treated as a fresh crossing, not
    # silently folded into the first (module docstring, point 12).
    gracie.process_readings({"temp_c": 56}, timestamp=2)  # delta=4
    assert gracie._last_readings["temp_c"]["severity"] == "FAULT"
    assert gracie._states["temp_c"].level_crossing_active is True

    # Point 13: this second crossing IS now announced on chester/watch
    # (so it can be forwarded to the orchestrator -- see
    # agents/escalation_watch.py), unlike the first crossing or the
    # settle-back in between. The latch itself is still untouched.
    assert len(chester) == 1, chester
    assert chester[0]["kind"] == "new_crossing_while_latched", chester[0]
    assert chester[0]["channel"] == "temp_c"
    print("  ok: a new crossing while already latched FAULT logs and announces a fresh event, latch stays unchanged")


def test_expected_cause_logs_not_flags_but_never_downgrades_fault():
    gracie, _, _ = make_gracie()
    # Expected cause present, size unknown (None) -- point 12's
    # original behaviour, preserved exactly: a crossing is logged
    # (WARNING), not flagged.
    gracie.process_readings({"temp_c": 56}, timestamp=0, expected_causes={"temp_c": None})
    assert gracie._last_readings["temp_c"]["severity"] == "WARNING"
    assert gracie.health_state == "WARNING"

    gracie.clear_fault("temp_c")
    assert gracie._last_readings["temp_c"]["severity"] == "NOMINAL"

    # No expected cause this time -- the same crossing actually flags it.
    gracie.process_readings({"temp_c": 56}, timestamp=1)
    assert gracie._last_readings["temp_c"]["severity"] == "FAULT"

    # An expected cause on a LATER cycle must never downgrade an
    # existing FAULT latch -- same one-way-ratchet rule as everywhere
    # else in this file.
    gracie.process_readings({"temp_c": 56}, timestamp=2, expected_causes={"temp_c": None})
    assert gracie._last_readings["temp_c"]["severity"] == "FAULT", \
        "expected cause must never downgrade an existing FAULT latch"
    print("  ok: expected cause logs instead of flagging, but never downgrades an existing FAULT latch")


def test_expected_cause_with_size_only_excuses_a_value_actually_inside_it():
    """Point 13: an expected cause that carries a known expected size
    only excuses a crossing whose value is actually inside that
    range. A cause commanded at the WRONG size is not excused -- it
    is flagged, the same as an unexplained crossing."""
    gracie, _, _ = make_gracie()
    # Value (56) is inside the given expected range -- logged, not flagged.
    gracie.process_readings({"temp_c": 56}, timestamp=0, expected_causes={"temp_c": (50.0, 60.0)})
    assert gracie._last_readings["temp_c"]["severity"] == "WARNING"
    gracie.clear_fault("temp_c")

    # Value (80) is OUTSIDE the given expected range -- a cause was
    # commanded, but at the wrong size, so it is flagged exactly like
    # an unexplained crossing (e.g. bad_engine_burn in sim/RESULTS.md).
    gracie.process_readings({"temp_c": 80}, timestamp=1, expected_causes={"temp_c": (50.0, 60.0)})
    assert gracie._last_readings["temp_c"]["severity"] == "FAULT", \
        "a cause commanded at the wrong size must not be excused"
    print("  ok: an expected cause with a known size only excuses a value actually inside it")


def test_stillness_flags_a_sensor_that_never_varies_enough():
    """STUCK_RULE: stuck_window_seconds=5.0, min_normal_noise=2.0.
    Level/jump/leash are all set unreachable on this channel, so only
    Stillness can produce a FAULT here."""
    gracie, _, _ = make_gracie()
    readings = [10.0, 10.5, 11.0, 10.8, 10.3, 10.6]  # range 1.0, under the 2.0 minimum
    for t, v in enumerate(readings):
        gracie.process_readings({"stuck_channel": v}, timestamp=float(t))
        if t < 5:
            # Window doesn't cover the full 5.0s yet -- no verdict possible.
            assert gracie._last_readings["stuck_channel"]["sensor_health_fault"] is False

    assert gracie._last_readings["stuck_channel"]["severity"] == "FAULT"
    assert gracie._last_readings["stuck_channel"]["sensor_health_fault"] is True, \
        "a Stillness fault must be tagged distinctly from an ordinary level/leash fault"
    print("  ok: a sensor whose variation stays below the blueprint's minimum is flagged, tagged sensor-health")


def test_stillness_does_not_fire_on_a_sensor_that_varies_enough():
    gracie, _, _ = make_gracie()
    readings = [0.0, 5.0, 10.0, 3.0, 8.0, 1.0]  # range 10.0, well over the 2.0 minimum
    for t, v in enumerate(readings):
        gracie.process_readings({"stuck_channel": v}, timestamp=float(t))
    assert gracie._last_readings["stuck_channel"]["severity"] == "NOMINAL"
    assert gracie._last_readings["stuck_channel"]["sensor_health_fault"] is False
    print("  ok: a sensor with real variation never trips Stillness")


def test_allow_steady_exempts_a_channel_from_stillness():
    """STEADY_RULE has the SAME stuck_window_seconds/min_normal_noise
    as STUCK_RULE, but allow_steady=True -- SPEC.md: sensors that
    legitimately hold steady must say so in the blueprint, so they're
    judged correctly rather than flagged for being exactly as
    designed."""
    gracie, _, _ = make_gracie()
    readings = [10.0, 10.5, 11.0, 10.8, 10.3, 10.6]  # identical pattern to the STUCK_RULE test above
    for t, v in enumerate(readings):
        gracie.process_readings({"steady_channel": v}, timestamp=float(t))
    assert gracie._last_readings["steady_channel"]["severity"] == "NOMINAL"
    assert gracie._last_readings["steady_channel"]["sensor_health_fault"] is False
    print("  ok: allow_steady exempts a channel from Stillness entirely")


def test_stillness_latch_is_released_by_clear_fault():
    gracie, _, _ = make_gracie()
    readings = [10.0, 10.5, 11.0, 10.8, 10.3, 10.6]
    for t, v in enumerate(readings):
        gracie.process_readings({"stuck_channel": v}, timestamp=float(t))
    assert gracie._last_readings["stuck_channel"]["severity"] == "FAULT"
    assert gracie._last_readings["stuck_channel"]["sensor_health_fault"] is True

    gracie.clear_fault("stuck_channel")
    assert gracie._last_readings["stuck_channel"]["severity"] == "NOMINAL"
    assert gracie._last_readings["stuck_channel"]["sensor_health_fault"] is False
    print("  ok: clear_fault releases a Stillness latch, same as any other")


def test_causing_sense_is_level():
    gracie, _, _ = make_gracie()
    gracie.process_readings({"temp_c": 30}, timestamp=0)
    assert gracie._last_readings["temp_c"]["causing_sense"] is None

    gracie.process_readings({"temp_c": 56}, timestamp=1)
    assert gracie._last_readings["temp_c"]["causing_sense"] == "level"

    # Drops back in bounds -- the ratchet stays, and so must its cause.
    gracie.process_readings({"temp_c": 30}, timestamp=2)
    assert gracie._last_readings["temp_c"]["severity"] == "FAULT"
    assert gracie._last_readings["temp_c"]["causing_sense"] == "level"

    gracie.clear_fault("temp_c")
    assert gracie._last_readings["temp_c"]["causing_sense"] is None
    print("  ok: causing_sense is 'level' for a level crossing, persists until clear_fault")


def test_causing_sense_is_leash_soft_then_leash_hard():
    gracie, _, _ = make_gracie()
    for t in range(0, 51):
        gracie.process_readings({"drift_channel": 2.0 * t}, timestamp=float(t))
        cause = gracie._last_readings["drift_channel"]["causing_sense"]
        if t < 30:
            assert cause is None, (t, cause)
        elif t < 50:
            assert cause == "leash_soft", (t, cause)
        else:
            assert cause == "leash_hard", (t, cause)
    print("  ok: causing_sense tracks leash_soft, then switches to leash_hard once hard fires")


def test_causing_sense_is_stillness():
    gracie, _, _ = make_gracie()
    readings = [10.0, 10.5, 11.0, 10.8, 10.3, 10.6]  # range 1.0, under STUCK_RULE's 2.0 minimum
    for t, v in enumerate(readings):
        gracie.process_readings({"stuck_channel": v}, timestamp=float(t))
    assert gracie._last_readings["stuck_channel"]["causing_sense"] == "stillness"
    print("  ok: causing_sense is 'stillness' for a Stillness fault")


def test_causing_sense_never_becomes_jump():
    gracie, _, _ = make_gracie()
    gracie.process_readings({"temp_c": 0.0}, timestamp=0)
    gracie.process_readings({"temp_c": 40.0}, timestamp=1)  # a jump, well clear of TEMP_RULE's level bounds
    assert gracie._last_readings["temp_c"]["jump"] is True
    assert gracie._last_readings["temp_c"]["severity"] == "NOMINAL"
    assert gracie._last_readings["temp_c"]["causing_sense"] is None, \
        "jump never latches, so it must never become causing_sense"
    print("  ok: a jump alone never sets causing_sense -- it never touches latched_severity")


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
        test_clear_fault_default_resets_the_leash_timer,
        test_clear_fault_can_leave_the_leash_timer_running,
        test_leash_settles_back_before_hard_clears_and_announces_for_chester,
        test_leash_settles_back_stays_with_an_active_level_fault,
        test_leash_settles_back_stays_with_a_linked_channels_active_fault,
        test_jump_announces_on_chester_watch,
        test_clear_fault_announces_warning_left,
        test_report_carries_actual_readings,
        test_new_crossing_while_latched_logs_but_does_not_change_anything,
        test_expected_cause_logs_not_flags_but_never_downgrades_fault,
        test_expected_cause_with_size_only_excuses_a_value_actually_inside_it,
        test_stillness_flags_a_sensor_that_never_varies_enough,
        test_stillness_does_not_fire_on_a_sensor_that_varies_enough,
        test_allow_steady_exempts_a_channel_from_stillness,
        test_stillness_latch_is_released_by_clear_fault,
        test_causing_sense_is_level,
        test_causing_sense_is_leash_soft_then_leash_hard,
        test_causing_sense_is_stillness,
        test_causing_sense_never_becomes_jump,
        test_unrecognized_channel_is_ignored_not_guessed_at,
    ]
    for test in tests:
        test()
    print("All GRACIE any-sensor checks passed.")


if __name__ == "__main__":
    main()
