# sim/expected_cause_confirmation_test.py
# Added 2026-11-09 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Checks for ExpectedCauseConfirmation (EDEN expected-boom-readings
job, part A). Fakes gracie/eden with exactly the surface this class
actually reads/calls (_last_readings, fault_class_table,
react_to_fault_class) -- no real GracieAgent/EdenAgent construction
needed, same minimal-fake convention as agents/ghost_mode_test.py.

Run from the repo root:

    python -m sim.expected_cause_confirmation_test
"""
from agents.escalation_orchestrator import FaultClass
from sim.expected_cause_confirmation import ExpectedCauseConfirmation


class FakeGracie:
    def __init__(self):
        self._last_readings = {}


class FakeEden:
    def __init__(self, fault_class_table):
        self.fault_class_table = fault_class_table
        self.forced = []  # (fault_class, reason) pairs, in order

    def react_to_fault_class(self, fault_class, reason="GRACIE"):
        self.forced.append((fault_class, reason))


def reading(severity, causing_sense, excused, excused_by=None):
    return {"severity": severity, "causing_sense": causing_sense, "excused": excused, "excused_by": excused_by}


def test_confirmed_case_never_forces_eden():
    """Owner known, ground truth genuinely has a matching event active
    -- confirmed immediately, EDEN never forced, logged once."""
    gracie, eden = FakeGracie(), FakeEden({"engine_bay_temp": {"level": FaultClass.BOOM}})
    events = [{"kind": "engine_burn", "start_s": 100, "end_s": 200, "affected_channels": ["engine_bay_temp"]}]
    tracker = ExpectedCauseConfirmation(gracie, eden, events, {"engine_burn": "ETHAN"}, confirm_window_seconds=30.0)

    gracie._last_readings["engine_bay_temp"] = reading("WARNING", "level", True, excused_by="ETHAN")
    tracker.tick(150)
    assert eden.forced == [], "a confirmed excusal must never force EDEN's reaction"
    log = tracker.question_log()
    assert [e["outcome"] for e in log] == ["asked", "confirmed"], log
    print("  ok: owner known, ground truth confirms -- logged, EDEN never forced")


def test_unknown_owner_raises_immediately_no_window():
    """excused=True but excused_by=None -- nobody to ask. Raises on
    the very first tick, no waiting for the window at all."""
    gracie, eden = FakeGracie(), FakeEden({"solar_current": {"level": FaultClass.BOOM}})
    tracker = ExpectedCauseConfirmation(gracie, eden, events=[], event_owners={}, confirm_window_seconds=30.0)

    gracie._last_readings["solar_current"] = reading("WARNING", "level", True, excused_by=None)
    tracker.tick(0)
    assert eden.forced == [(FaultClass.BOOM, "UNCONFIRMED")], eden.forced
    log = tracker.question_log()
    assert [e["outcome"] for e in log] == ["asked", "raised_no_owner"], log
    print("  ok: unknown owner raises immediately, no window -- Jay's 'unknown owner = not confirmed = raise'")


def test_owner_known_ground_truth_disagrees_raises_after_window():
    """Owner known, but no matching event is ever active -- a fresh
    clock starts, and once confirm_window_seconds elapses with still
    no confirmation, EDEN is forced exactly once."""
    gracie, eden = FakeGracie(), FakeEden({"engine_bay_temp": {"level": FaultClass.BOOM}})
    tracker = ExpectedCauseConfirmation(
        gracie, eden, events=[], event_owners={"engine_burn": "ETHAN"}, confirm_window_seconds=30.0,
    )

    for t in range(0, 30):
        gracie._last_readings["engine_bay_temp"] = reading("WARNING", "level", True, excused_by="ETHAN")
        tracker.tick(t)
        assert eden.forced == [], f"must not force before the window elapses (t={t})"

    tracker.tick(30)  # elapsed == confirm_window_seconds exactly -- the window has now elapsed
    assert eden.forced == [(FaultClass.BOOM, "UNCONFIRMED")], eden.forced
    outcomes = [e["outcome"] for e in tracker.question_log()]
    assert outcomes[0] == "asked" and outcomes[-1] == "raised_timeout", outcomes
    assert outcomes.count("asked") == 1, "asked must log once per pending episode, not every tick"
    print("  ok: owner known but ground truth never confirms -- raises once the window elapses, not before")


def test_confirms_before_the_window_elapses_cancels_the_pending_raise():
    """The ground truth starts disagreeing, then starts agreeing
    before the window runs out -- confirmed, never raised."""
    gracie, eden = FakeGracie(), FakeEden({"engine_bay_temp": {"level": FaultClass.BOOM}})
    events = [{"kind": "engine_burn", "start_s": 10, "end_s": 20, "affected_channels": ["engine_bay_temp"]}]
    tracker = ExpectedCauseConfirmation(gracie, eden, events, {"engine_burn": "ETHAN"}, confirm_window_seconds=30.0)

    for t in range(0, 10):  # before the event starts -- ground truth disagrees
        gracie._last_readings["engine_bay_temp"] = reading("WARNING", "level", True, excused_by="ETHAN")
        tracker.tick(t)
    gracie._last_readings["engine_bay_temp"] = reading("WARNING", "level", True, excused_by="ETHAN")
    tracker.tick(10)  # event now active -- confirmed, well inside the 30s window
    assert eden.forced == [], eden.forced
    outcomes = [e["outcome"] for e in tracker.question_log()]
    assert outcomes == ["asked", "confirmed"], outcomes
    print("  ok: confirming before the window elapses cancels the pending raise")


def test_non_boom_excused_channel_is_never_tracked():
    """A MAJOR-classed channel's excusal is out of scope for this
    mechanism entirely (Jay's task is boom-specific) -- never asked,
    never raised, regardless of owner."""
    gracie, eden = FakeGracie(), FakeEden({"fuel_flow": {"level": FaultClass.MAJOR}})
    tracker = ExpectedCauseConfirmation(gracie, eden, events=[], event_owners={}, confirm_window_seconds=30.0)

    gracie._last_readings["fuel_flow"] = reading("WARNING", "level", True, excused_by=None)
    tracker.tick(0)
    assert eden.forced == []
    assert tracker.question_log() == []
    print("  ok: a non-boom channel's excusal is never tracked by this mechanism at all")


def test_leaving_the_excused_state_resets_the_pending_clock():
    """A channel that stops being excused (cleared, or genuinely
    flagged outright) before the window elapses must not carry its
    old clock into a LATER, separate excusal episode."""
    gracie, eden = FakeGracie(), FakeEden({"engine_bay_temp": {"level": FaultClass.BOOM}})
    tracker = ExpectedCauseConfirmation(
        gracie, eden, events=[], event_owners={"engine_burn": "ETHAN"}, confirm_window_seconds=30.0,
    )

    for t in range(0, 20):
        gracie._last_readings["engine_bay_temp"] = reading("WARNING", "level", True, excused_by="ETHAN")
        tracker.tick(t)
    # No longer excused for a while (e.g. back to NOMINAL) -- clears the pending clock.
    gracie._last_readings["engine_bay_temp"] = reading("NOMINAL", None, False)
    tracker.tick(20)
    assert eden.forced == []

    # A fresh excusal episode starts its OWN clock from scratch, not
    # continuing the old one (which was already at 20/30s).
    for t in range(21, 40):
        gracie._last_readings["engine_bay_temp"] = reading("WARNING", "level", True, excused_by="ETHAN")
        tracker.tick(t)
        assert eden.forced == [], f"the fresh episode's own clock must not inherit the old elapsed time (t={t})"
    tracker.tick(51)  # 30s after the fresh episode's own start at t=21
    assert eden.forced == [(FaultClass.BOOM, "UNCONFIRMED")], eden.forced
    print("  ok: leaving the excused state resets the pending clock for the next episode")


def main():
    tests = [
        test_confirmed_case_never_forces_eden,
        test_unknown_owner_raises_immediately_no_window,
        test_owner_known_ground_truth_disagrees_raises_after_window,
        test_confirms_before_the_window_elapses_cancels_the_pending_raise,
        test_non_boom_excused_channel_is_never_tracked,
        test_leaving_the_excused_state_resets_the_pending_clock,
    ]
    for test in tests:
        test()
    print("All ExpectedCauseConfirmation checks passed.")


if __name__ == "__main__":
    main()
