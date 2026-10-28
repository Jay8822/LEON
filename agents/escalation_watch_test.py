# agents/escalation_watch_test.py
# Added 2026-10-27 — Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Checks for EscalationWatch (Item 3b: "new crossing while already
latched" reaching the orchestrator). Same testing conventions as
agents/ghost_mode_test.py -- real EventBus, real EscalationOrchestrator
with placeholder windows, real GracieAgent where the test needs one.

Run from the repo root:

    python -m agents.escalation_watch_test
"""

from agents.escalation_orchestrator import EscalationOrchestrator
from agents.escalation_watch import EscalationWatch
from agents.gracie import GracieAgent
from agents.gracie_rulebook import ChannelRule
from core.bus import EventBus

TEST_MAJOR_WINDOW_SECONDS = 5.0
TEST_NON_URGENT_WINDOW_SECONDS = 30.0
TEST_LIGHT_FLAG_CYCLE_MINUTES = 15.0


def make_orchestrator(**kwargs):
    kwargs.setdefault("major_fault_window_seconds", TEST_MAJOR_WINDOW_SECONDS)
    kwargs.setdefault("non_urgent_fault_window_seconds", TEST_NON_URGENT_WINDOW_SECONDS)
    kwargs.setdefault("light_flag_cycle_minutes", TEST_LIGHT_FLAG_CYCLE_MINUTES)
    # triage() is skipped (see escalation_watch.py module docstring),
    # so these can stay empty, same convention as ghost_mode_test.py.
    return EscalationOrchestrator(eden_rules={}, own_rules={}, **kwargs)


def make_gracie_and_watch():
    bus = EventBus()
    rule = ChannelRule(
        name="temp_c", units="C",
        level_high=55.0, level_low=-20.0,
        jump_limit=1000.0,
        leash_window_seconds=1.0, leash_slope_limit=1000.0,
        leash_soft_duration_seconds=1000.0, leash_hard_duration_seconds=2000.0,
        stuck_window_seconds=1.0, min_normal_noise=0.0,  # Stillness not exercised here
        level_fault_class=None, jump_fault_class=None, leash_soft_fault_class=None,
        leash_hard_fault_class=None, stillness_fault_class=None,  # Item C: not stated this round
    )
    gracie = GracieAgent(bus, {"temp_c": rule})
    orchestrator = make_orchestrator()
    watch = EscalationWatch(bus, orchestrator)
    return bus, gracie, orchestrator, watch


def test_new_crossing_while_latched_reaches_the_orchestrator():
    bus, gracie, orchestrator, watch = make_gracie_and_watch()
    gracie.process_readings({"temp_c": 56}, timestamp=0)  # first crossing -> FAULT, no escalation yet
    assert watch.forwarded_log() == []

    gracie.process_readings({"temp_c": 52}, timestamp=1)  # back in bounds -- still latched
    assert watch.forwarded_log() == []

    gracie.process_readings({"temp_c": 56}, timestamp=2)  # second, separate crossing while still latched
    forwarded = watch.forwarded_log()
    assert len(forwarded) == 1, forwarded
    assert forwarded[0]["channel"] == "temp_c"
    assert forwarded[0]["outcome"] == "EDEN", forwarded[0]

    orchestrator_log = orchestrator.decision_log()
    assert any(e["detail"] == "VIOLATED -> EDEN" for e in orchestrator_log), orchestrator_log
    print("  ok: a new crossing while already latched reaches the orchestrator, straight to EDEN")


def test_every_other_chester_watch_kind_is_ignored():
    """jump, leash_settled, warning_entered, warning_left -- none of
    these should ever reach the orchestrator through this file; they
    already have their own handling (GRACIE's own latching, CHESTER's
    watch)."""
    bus, gracie, orchestrator, watch = make_gracie_and_watch()
    for kind in ("jump", "leash_settled", "warning_entered", "warning_left"):
        bus.publish("chester/watch", {
            "kind": kind, "agent": "GRACIE", "channel": "temp_c",
            "timestamp": 0, "readings": {},
        })
    assert watch.forwarded_log() == []
    assert orchestrator.decision_log() == []
    print("  ok: every other chester/watch kind is ignored -- only new_crossing_while_latched escalates")


def test_a_first_crossing_never_escalates_only_a_later_one_does():
    """The ordinary first "LEVEL transition -> FAULT" case must never
    reach the orchestrator through this path -- only the second,
    separate crossing while already latched does (SPEC.md: a *new*
    event while latched, not the original one)."""
    bus, gracie, orchestrator, watch = make_gracie_and_watch()
    gracie.process_readings({"temp_c": 56}, timestamp=0)
    gracie.clear_fault("temp_c")
    gracie.process_readings({"temp_c": 56}, timestamp=1)  # fresh first crossing, not "while latched"
    assert watch.forwarded_log() == []
    print("  ok: an ordinary first crossing never escalates on its own")


class _ExplodingOrchestrator:
    """Stand-in that always raises, to prove a harness-side failure
    never reaches GRACIE or the bus -- same safety requirement as
    ghost_mode.py's own test."""
    def decide(self, report, severity):
        raise RuntimeError("simulated escalation-watch failure")

    def decision_log(self):
        return []


def test_watch_failure_never_affects_gracie_or_the_bus():
    bus = EventBus()
    rule = ChannelRule(
        name="temp_c", units="C",
        level_high=55.0, level_low=-20.0,
        jump_limit=1000.0,
        leash_window_seconds=1.0, leash_slope_limit=1000.0,
        leash_soft_duration_seconds=1000.0, leash_hard_duration_seconds=2000.0,
        stuck_window_seconds=1.0, min_normal_noise=0.0,
        level_fault_class=None, jump_fault_class=None, leash_soft_fault_class=None,
        leash_hard_fault_class=None, stillness_fault_class=None,  # Item C: not stated this round
    )
    gracie = GracieAgent(bus, {"temp_c": rule})
    watch = EscalationWatch(bus, _ExplodingOrchestrator())

    gracie.process_readings({"temp_c": 56}, timestamp=0)
    gracie.process_readings({"temp_c": 52}, timestamp=1)
    gracie.process_readings({"temp_c": 56}, timestamp=2)  # triggers the escalation attempt, which raises internally

    assert gracie._last_readings["temp_c"]["severity"] == "FAULT", \
        "GRACIE must be unaffected by a failure in a downstream watcher"
    assert watch.forwarded_log() == []  # failed before it could record anything
    print("  ok: a watch-side failure is swallowed and logged -- GRACIE still reacts normally")


def main():
    tests = [
        test_new_crossing_while_latched_reaches_the_orchestrator,
        test_every_other_chester_watch_kind_is_ignored,
        test_a_first_crossing_never_escalates_only_a_later_one_does,
        test_watch_failure_never_affects_gracie_or_the_bus,
    ]
    for test in tests:
        test()
    print("All EscalationWatch checks passed.")


if __name__ == "__main__":
    main()
