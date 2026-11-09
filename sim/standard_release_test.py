# sim/standard_release_test.py
# Added 2026-11-09 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Checks for StandardRelease (fault-clearing job, part B). Fakes
gracie/eden with exactly the surface this class reads/calls
(_last_readings, clear_fault, fault_class_table, confirm_settled) --
same minimal-fake convention as sim/expected_cause_confirmation_test.py.

Run from the repo root:

    python -m sim.standard_release_test
"""
from agents.escalation_orchestrator import FaultClass
from sim.standard_release import StandardRelease


class FakeGracie:
    def __init__(self):
        self._last_readings = {}
        self.cleared = []  # channel names, in order

    def clear_fault(self, channel):
        self.cleared.append(channel)
        self._last_readings[channel]["severity"] = "NOMINAL"


class FakeEden:
    def __init__(self, fault_class_table, confirms=True):
        self.fault_class_table = fault_class_table
        self._confirms = confirms  # bool, or a callable(channel, value) -> bool
        self.confirm_calls = []

    def confirm_settled(self, channel, value):
        self.confirm_calls.append((channel, value))
        if callable(self._confirms):
            return self._confirms(channel, value)
        return self._confirms


def reading(severity, causing_sense=None, value=0.0):
    return {"severity": severity, "causing_sense": causing_sense, "value": value}


def test_releases_once_settled_and_confirmed():
    gracie, eden = FakeGracie(), FakeEden({"fuel_flow": {"leash_hard": FaultClass.MAJOR}})
    tracker = StandardRelease(gracie, eden, faults=[], settle_time_seconds=10.0)

    for t in range(0, 10):
        gracie._last_readings["fuel_flow"] = reading("FAULT", "leash_hard", value=5.0)
        tracker.tick(t)
        assert gracie.cleared == [], f"must not release before settle_time_seconds (t={t})"

    tracker.tick(10)
    assert gracie.cleared == ["fuel_flow"], gracie.cleared
    outcomes = [e["outcome"] for e in tracker.question_log()]
    assert outcomes == ["asked", "released"], outcomes
    print("  ok: releases once the channel has settled for settle_time_seconds and EDEN confirms")


def test_never_releases_while_the_fault_is_still_live():
    gracie, eden = FakeGracie(), FakeEden({"fuel_flow": {"leash_hard": FaultClass.MAJOR}})
    faults = [{"channel": "fuel_flow", "start_s": 0, "end_s": 50}]
    tracker = StandardRelease(gracie, eden, faults=faults, settle_time_seconds=10.0)

    for t in range(0, 30):
        gracie._last_readings["fuel_flow"] = reading("FAULT", "leash_hard", value=5.0)
        tracker.tick(t)
    assert gracie.cleared == [], "must never release while the real fault is still live, no matter how long"
    assert tracker.question_log() == [], "must not even start asking while still live"
    print("  ok: never releases while the fault is still live, however long it's been latched")


def test_eden_not_confirming_withholds_release():
    """EDEN's own independent check can say no even once settled and
    past the window -- release must wait for her, not just the timer."""
    gracie = FakeGracie()
    eden = FakeEden({"fuel_flow": {"leash_hard": FaultClass.MAJOR}}, confirms=False)
    tracker = StandardRelease(gracie, eden, faults=[], settle_time_seconds=10.0)

    for t in range(0, 20):
        gracie._last_readings["fuel_flow"] = reading("FAULT", "leash_hard", value=5.0)
        tracker.tick(t)
    assert gracie.cleared == [], "EDEN never confirmed -- must not release regardless of elapsed time"
    assert len(eden.confirm_calls) > 1, "EDEN should be re-asked on later ticks, not asked once and given up on"
    print("  ok: withholds release for as long as EDEN's own check disagrees, however long that takes")


def test_going_live_again_resets_the_settle_clock():
    """Quiet for 5s (short of the 10s settle_time_seconds -- no
    release yet), then the SAME fault goes live again for 5s, then
    quiet again. Release must count only from the SECOND quiet
    period's own start (t=10), not resume the first 5s where it left
    off -- otherwise it would wrongly release at t=10+5=15 instead of
    the correct t=10+10=20."""
    gracie, eden = FakeGracie(), FakeEden({"fuel_flow": {"leash_hard": FaultClass.MAJOR}})
    faults = [{"channel": "fuel_flow", "start_s": 5, "end_s": 10}]
    tracker = StandardRelease(gracie, eden, faults=faults, settle_time_seconds=10.0)

    for t in range(0, 5):  # quiet, but short of settle_time_seconds
        gracie._last_readings["fuel_flow"] = reading("FAULT", "leash_hard", value=5.0)
        tracker.tick(t)
    for t in range(5, 10):  # the same fault goes live again
        gracie._last_readings["fuel_flow"] = reading("FAULT", "leash_hard", value=5.0)
        tracker.tick(t)
    assert gracie.cleared == [], "must not release while live, nor from residual time once it ends"

    for t in range(10, 20):  # quiet again -- must NOT release at 10+5=15 (the old, wrongly-resumed clock)
        gracie._last_readings["fuel_flow"] = reading("FAULT", "leash_hard", value=5.0)
        tracker.tick(t)
        assert gracie.cleared == [], f"must not release before a FRESH 10s of quiet has passed (t={t})"

    gracie._last_readings["fuel_flow"] = reading("FAULT", "leash_hard", value=5.0)
    tracker.tick(20)  # 10s after the second quiet period's own start at t=10 (not the original t=0)
    assert gracie.cleared == ["fuel_flow"], gracie.cleared
    print("  ok: going live again resets the settle clock, not resuming where it left off")


def test_boom_classed_channel_is_never_tracked_here():
    """Boom faults release via the (narrowed) four-way sign-off, not
    this mechanism -- a boom-classed latch must never be released by
    StandardRelease, however long it's settled."""
    gracie, eden = FakeGracie(), FakeEden({"engine_bay_temp": {"level": FaultClass.BOOM}})
    tracker = StandardRelease(gracie, eden, faults=[], settle_time_seconds=10.0)

    for t in range(0, 30):
        gracie._last_readings["engine_bay_temp"] = reading("FAULT", "level", value=5.0)
        tracker.tick(t)
    assert gracie.cleared == []
    assert tracker.question_log() == []
    print("  ok: a boom-classed channel is never released by this mechanism")


def test_nominal_channel_is_never_tracked():
    gracie, eden = FakeGracie(), FakeEden({})
    tracker = StandardRelease(gracie, eden, faults=[], settle_time_seconds=10.0)
    for t in range(0, 15):
        gracie._last_readings["fuel_flow"] = reading("NOMINAL")
        tracker.tick(t)
    assert gracie.cleared == []
    assert tracker.question_log() == []
    print("  ok: a channel that's never latched is never asked about at all")


def main():
    tests = [
        test_releases_once_settled_and_confirmed,
        test_never_releases_while_the_fault_is_still_live,
        test_eden_not_confirming_withholds_release,
        test_going_live_again_resets_the_settle_clock,
        test_boom_classed_channel_is_never_tracked_here,
        test_nominal_channel_is_never_tracked,
    ]
    for test in tests:
        test()
    print("All StandardRelease checks passed.")


if __name__ == "__main__":
    main()
