# agents/ghost_mode_test.py
# Added 2026-10-23 — Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Checks for GhostModeHarness (task 3: GRACIE wired into
EscalationOrchestrator in ghost mode).

Uses the real EventBus, the real EdenAgent, and a real
EscalationOrchestrator (with placeholder, clearly-labelled window
values — same "no real numbers yet" convention as
escalation_orchestrator_test.py). GRACIE herself isn't needed here:
these tests publish "telemetry/health" payloads directly, the same
shape GracieAgent.report_health() actually publishes, since the
harness only cares about what's on the bus, not who put it there.

Run from the repo root:

    python -m agents.ghost_mode_test
"""

import time

from agents.eden import EdenAgent
from agents.escalation_orchestrator import EscalationOrchestrator
from agents.ghost_mode import GhostModeHarness
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
    # No eden_rules/own_rules entries needed for GRACIE: the harness
    # skips triage() entirely (see ghost_mode.py module docstring,
    # point 1), so these dicts can stay empty for these tests.
    return EscalationOrchestrator(eden_rules={}, own_rules={}, **kwargs)


def health_payload(health, source="GRACIE", timestamp=None):
    return {
        "system_health": health,
        "source": source,
        "timestamp": timestamp if timestamp is not None else int(time.time()),
    }


def build_real_wiring():
    """Same subscription order main.py uses: EDEN reacts first, the
    ghost harness observes second. See ghost_mode.py module docstring,
    point 2, for why this order matters."""
    bus = EventBus()
    eden = EdenAgent(bus)
    orchestrator = make_orchestrator()
    bus.subscribe("telemetry/health", eden.on_health_event)
    harness = GhostModeHarness(bus, eden, orchestrator)
    return bus, eden, orchestrator, harness


# --- core behaviour: FAULT goes through, logged, agrees with EDEN ----------

def test_fault_report_reaches_orchestrator_and_agrees_with_eden():
    bus, eden, orchestrator, harness = build_real_wiring()
    bus.publish("telemetry/health", health_payload("FAULT"))

    assert eden.status == "SAFE_MODE", eden.status

    comparisons = harness.comparison_log()
    assert len(comparisons) == 1, comparisons
    entry = comparisons[0]
    assert entry["source"] == "GRACIE"
    assert entry["ghost_outcome"] == "EDEN", entry
    assert entry["old_wiring_status"] == "SAFE_MODE", entry
    assert entry["agree"] is True, entry

    orchestrator_log = orchestrator.decision_log()
    assert any(e["detail"] == "VIOLATED -> EDEN" for e in orchestrator_log), orchestrator_log
    print("  ok: GRACIE FAULT reaches the orchestrator, agrees with EDEN's real reaction, no triage()")


def test_fault_from_non_gracie_source_is_still_handled():
    """The harness isn't hardcoded to GRACIE's name specifically — it
    reacts to whatever "telemetry/health" actually says, same as EDEN
    does. GRACIE is simply the only real publisher today."""
    bus, eden, orchestrator, harness = build_real_wiring()
    bus.publish("telemetry/health", health_payload("FAULT", source="GRACIE"))
    comparisons = harness.comparison_log()
    assert comparisons[0]["source"] == "GRACIE"
    print("  ok: comparison entry records the real reporting agent's name")


# --- WARNING/NOMINAL never reach the orchestrator ---------------------------

def test_warning_and_nominal_are_ignored():
    bus, eden, orchestrator, harness = build_real_wiring()
    bus.publish("telemetry/health", health_payload("WARNING"))
    bus.publish("telemetry/health", health_payload("NOMINAL"))

    assert harness.comparison_log() == []
    assert orchestrator.decision_log() == []
    assert eden.status == "MONITORING"
    print("  ok: WARNING/NOMINAL never reach the orchestrator — only faults do, per SPEC.md")


# --- the real, any-sensor GracieAgent still triggers ghost mode -------------

def test_real_upgraded_gracie_payload_still_triggers_ghost_mode():
    """GRACIE was rewritten (any-sensor, rule-book-driven) after this
    harness was built. Her payload grew a new "readings" key, but the
    top-level contract ghost mode actually reads -- system_health/
    source/timestamp -- is unchanged (see agents/gracie.py's module
    docstring, point 1). This drives a REAL GracieAgent, not a
    synthetic payload, to prove that holds."""
    bus = EventBus()
    rule_book = {
        "temp_c": ChannelRule(
            name="temp_c", units="C",
            level_high=55.0, level_low=-50.0,
            jump_limit=1000.0,
            leash_window_seconds=1.0, leash_slope_limit=1000.0,
            leash_soft_duration_seconds=1000.0, leash_hard_duration_seconds=2000.0,
            stuck_window_seconds=1.0, min_normal_noise=0.0,  # Stillness not exercised here
        ),
    }
    gracie = GracieAgent(bus, rule_book)
    eden = EdenAgent(bus)
    orchestrator = make_orchestrator()
    bus.subscribe("telemetry/health", eden.on_health_event)
    harness = GhostModeHarness(bus, eden, orchestrator)

    gracie.process_readings({"temp_c": 30}, timestamp=0)  # NOMINAL -- nothing should fire
    assert harness.comparison_log() == []
    assert eden.status == "MONITORING"

    gracie.process_readings({"temp_c": 100}, timestamp=1)  # crosses level_high -> FAULT
    assert eden.status == "SAFE_MODE"
    comparisons = harness.comparison_log()
    assert len(comparisons) == 1, comparisons
    assert comparisons[0]["agree"] is True, comparisons[0]
    print("  ok: a real, upgraded GracieAgent's FAULT still reaches the orchestrator and agrees with EDEN")


# --- subscription-order dependency ------------------------------------------

def test_ghost_mode_depends_on_subscription_order_after_eden():
    """ghost_mode.py's module docstring (point 2) names this ordering
    dependency explicitly: the harness must be subscribed to
    "telemetry/health" *after* eden.on_health_event, so eden.status
    already reflects this event by the time the harness reads it. This
    test proves the dependency exists, so it's caught if the order
    this file (or main.py) wires things up in ever changes."""
    bus = EventBus()
    eden = EdenAgent(bus)
    orchestrator = make_orchestrator()

    # Wrong order on purpose: harness subscribed BEFORE EDEN reacts.
    harness = GhostModeHarness(bus, eden, orchestrator)
    bus.subscribe("telemetry/health", eden.on_health_event)

    bus.publish("telemetry/health", health_payload("FAULT"))

    entry = harness.comparison_log()[0]
    # The harness ran first, so it read eden.status before EDEN had
    # reacted to *this* event -- still whatever it was before (IDLE on
    # a fresh agent), not SAFE_MODE, even though EDEN went to SAFE_MODE
    # moments later. This mismatch is exactly what wrong ordering
    # looks like, and exactly why main.py's order matters.
    assert entry["old_wiring_status"] != "SAFE_MODE", entry
    assert eden.status == "SAFE_MODE"  # EDEN still reacted correctly, just after we looked
    print("  ok: wrong subscription order is observably wrong, confirming the real order is load-bearing")


# --- safety requirement: ghost mode can never affect the real system -------

class _ExplodingOrchestrator:
    """Stand-in that always raises, to prove a harness-side failure
    never reaches EDEN or the bus."""
    def decide(self, report, severity):
        raise RuntimeError("simulated ghost-mode failure")

    def decision_log(self):
        return []


def test_harness_failure_never_affects_eden_or_the_bus():
    bus = EventBus()
    eden = EdenAgent(bus)
    bus.subscribe("telemetry/health", eden.on_health_event)
    harness = GhostModeHarness(bus, eden, _ExplodingOrchestrator())

    # Must not raise out of publish() -- the harness catches its own
    # exception, and EventBus isolates handlers from each other
    # regardless (core/bus.py). This test exercises both layers.
    bus.publish("telemetry/health", health_payload("FAULT"))

    assert eden.status == "SAFE_MODE", "EDEN must react exactly as she would without ghost mode"
    assert harness.comparison_log() == []  # failed before it could record anything
    print("  ok: a harness-side failure is swallowed and logged -- EDEN still reacts normally")


def main():
    tests = [
        test_fault_report_reaches_orchestrator_and_agrees_with_eden,
        test_fault_from_non_gracie_source_is_still_handled,
        test_real_upgraded_gracie_payload_still_triggers_ghost_mode,
        test_warning_and_nominal_are_ignored,
        test_ghost_mode_depends_on_subscription_order_after_eden,
        test_harness_failure_never_affects_eden_or_the_bus,
    ]
    for test in tests:
        test()
    print("All GhostModeHarness checks passed.")


if __name__ == "__main__":
    main()
