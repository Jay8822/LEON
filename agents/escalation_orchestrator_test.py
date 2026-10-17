# agents/escalation_orchestrator_test.py
# Added 2026-08-01 — Jay Pratt + AI (Claude, Anthropic).
"""Checks for EscalationOrchestrator, one per step of SPEC.md's
"Escalation chain (in order)", plus the bypass rule and the logging
requirement.

Everything here is synthetic: fake RuleSets and hand-built AgentReport
objects, not real GracieAgent/EthanAgent/etc. output. That's deliberate
(see agents/escalation_orchestrator.py's module docstring) — this
component is self-contained in this pass, and these are example/
fixture values, not claims about real spacecraft thresholds.

Steps 1 (self-check) and 2 (load varies by mission phase) have no test
here because SPEC.md assigns both to agent-owned behaviour / mission
context, not orchestrator logic — there is nothing on this class to
exercise for them. See the escalation_orchestrator.py module docstring.

Run from the repo root:

    python -m agents.escalation_orchestrator_test
"""

from agents.escalation_orchestrator import (
    AgentReport,
    BypassReason,
    Consensus,
    EscalationOrchestrator,
    Severity,
)


class AlwaysViolated:
    """Fixture rule: everything is a violation. Not a real threshold."""
    def check(self, report):
        return Severity.VIOLATED


class AlwaysNominal:
    """Fixture rule: everything is fine. Not a real threshold."""
    def check(self, report):
        return Severity.NOMINAL


class ThresholdRule:
    """Fixture rule shaped like a real one would be: flags when
    report.value exceeds `limit`. `limit` here is an arbitrary example
    for the test, not a real spacecraft parameter."""
    def __init__(self, limit):
        self.limit = limit

    def check(self, report):
        return Severity.VIOLATED if report.value > self.limit else Severity.NOMINAL


def make_orchestrator(agent_rule, own_rule, **kwargs):
    return EscalationOrchestrator(
        eden_rules={"GRACIE": agent_rule},
        own_rules={"GRACIE": own_rule},
        **kwargs,
    )


def report(agent="GRACIE", value=0, bypass=None):
    return AgentReport(agent=agent, value=value, bypass=bypass)


# --- step 3: unresolved items go to the orchestrator first -----------------

def test_step3_intake_routes_through_triage_and_decide():
    orch = make_orchestrator(AlwaysNominal(), AlwaysNominal())
    result = orch.intake(report())
    assert result.outcome == "CLEAR", result
    assert result.reason == "nominal", result

    orch = make_orchestrator(AlwaysViolated(), AlwaysViolated())
    result = orch.intake(report())
    assert result.outcome == "EDEN", result
    assert result.reason == "violated_outright", result
    print("  ok: step 3 — intake() routes a normal report through triage+decide")


# --- step 4: orchestrator checks (violated outright vs conflicting) --------

def test_step4_triage_classification():
    both_violated = make_orchestrator(AlwaysViolated(), AlwaysViolated())
    assert both_violated.triage(report()) == Severity.VIOLATED

    both_nominal = make_orchestrator(AlwaysNominal(), AlwaysNominal())
    assert both_nominal.triage(report()) == Severity.NOMINAL

    disagreeing = make_orchestrator(AlwaysViolated(), AlwaysNominal())
    assert disagreeing.triage(report()) == Severity.AMBIGUOUS

    disagreeing2 = make_orchestrator(AlwaysNominal(), AlwaysViolated())
    assert disagreeing2.triage(report()) == Severity.AMBIGUOUS

    # Realistic-shaped example: value 15 against two different example limits.
    threshold_mixed = make_orchestrator(ThresholdRule(limit=10), ThresholdRule(limit=20))
    assert threshold_mixed.triage(report(value=15)) == Severity.AMBIGUOUS
    print("  ok: step 4 — triage() requires both rule sets to agree for VIOLATED/NOMINAL")


# --- step 5: orchestrator decides (EDEN vs rerun) ---------------------------

def test_step5_decide_outcomes():
    orch = make_orchestrator(AlwaysNominal(), AlwaysNominal())

    violated = orch.decide(report(), Severity.VIOLATED)
    assert violated.outcome == "EDEN" and violated.reason == "violated_outright"

    nominal = orch.decide(report(), Severity.NOMINAL)
    assert nominal.outcome == "CLEAR" and nominal.reason == "nominal"

    ambiguous = orch.decide(report(), Severity.AMBIGUOUS)
    assert ambiguous.outcome == "RERUN_REQUESTED" and ambiguous.reason == "ambiguous"
    print("  ok: step 5 — decide() sends VIOLATED to EDEN, AMBIGUOUS to rerun, NOMINAL clears")


# --- step 6: rerun ladder ----------------------------------------------------

def test_step6_rerun_stable_result_escalates():
    orch = make_orchestrator(AlwaysNominal(), AlwaysNominal())
    r = report()
    orch.decide(r, Severity.AMBIGUOUS)  # seeds history with the original check
    result = orch.record_rerun(r, Severity.AMBIGUOUS)  # same result twice
    assert result.outcome == "EDEN" and result.reason == "rerun_stable", result
    print("  ok: step 6a — same result twice (rerun matches the original) -> EDEN")


def test_step6_rerun_differs_then_stabilizes():
    orch = make_orchestrator(AlwaysNominal(), AlwaysNominal())
    r = report()
    orch.decide(r, Severity.AMBIGUOUS)
    first = orch.record_rerun(r, Severity.VIOLATED)  # differs from original
    assert first.outcome == "RERUN_REQUESTED" and first.reason == "rerun_differs", first
    second = orch.record_rerun(r, Severity.VIOLATED)  # matches the previous rerun
    assert second.outcome == "EDEN" and second.reason == "rerun_stable", second
    print("  ok: step 6b — differs once, then stabilizes -> rerun again, then EDEN")


def test_step6_rerun_keeps_differing_escalates_regardless():
    orch = make_orchestrator(AlwaysNominal(), AlwaysNominal(), max_reruns=3)
    r = report()
    orch.decide(r, Severity.AMBIGUOUS)  # check #1: AMBIGUOUS
    first = orch.record_rerun(r, Severity.VIOLATED)  # check #2: differs
    assert first.outcome == "RERUN_REQUESTED", first
    second = orch.record_rerun(r, Severity.NOMINAL)  # check #3: differs again
    assert second.outcome == "EDEN" and second.reason == "rerun_unstable", second
    print("  ok: step 6c — keeps differing past max_reruns -> EDEN regardless of parameters")


# --- step 7 / 8: consensus (clear path / unclear path) ----------------------

def test_step7_all_clear_releases():
    orch = make_orchestrator(AlwaysNominal(), AlwaysNominal())
    entries = [
        (report(agent="LUNAE"), Consensus.CLEAR),
        (report(agent="ETHAN"), Consensus.CLEAR),
    ]
    result = orch.consensus(entries)
    assert result.outcome == "CLEAR" and result.reason == "consensus_clear", result
    releases = [e for e in orch.decision_log() if e["kind"] == "release"]
    assert {e["agent"] for e in releases} == {"LUNAE", "ETHAN"}, releases
    print("  ok: step 7 — every involved agent all-clear -> release, logged for each")


def test_step8_any_dissent_goes_to_human():
    orch = make_orchestrator(AlwaysNominal(), AlwaysNominal())
    entries = [
        (report(agent="LUNAE"), Consensus.CLEAR),
        (report(agent="ETHAN"), Consensus.UNCLEAR),
    ]
    result = orch.consensus(entries)
    assert result.outcome == "HUMAN" and result.reason == "dissent:ETHAN", result
    print("  ok: step 8 — one dissenting agent is enough to escalate to a human")


# --- step 9: timeout / process-count floor -----------------------------------

def test_step9_process_count_floor():
    orch = make_orchestrator(AlwaysNominal(), AlwaysNominal(), process_count_floor=5)
    assert orch.check_floor(report(), process_count=3, elapsed_seconds=1.0) is None
    result = orch.check_floor(report(), process_count=6, elapsed_seconds=1.0)
    assert result.outcome == "HUMAN" and result.reason == "timeout_floor", result
    print("  ok: step 9a — process-count floor escalates to human once crossed")


def test_step9_timeout_floor():
    orch = make_orchestrator(AlwaysNominal(), AlwaysNominal(), timeout_seconds=60.0)
    assert orch.check_floor(report(), process_count=1, elapsed_seconds=10.0) is None
    result = orch.check_floor(report(), process_count=1, elapsed_seconds=61.0)
    assert result.outcome == "HUMAN" and result.reason == "timeout_floor", result
    print("  ok: step 9b — time floor escalates to human once crossed, independent of process count")


# --- bypass rule --------------------------------------------------------------

def test_bypass_ethan_need_human_now():
    orch = make_orchestrator(AlwaysNominal(), AlwaysNominal())
    r = report(agent="ETHAN", bypass=BypassReason.ETHAN_NEED_HUMAN_NOW)
    result = orch.intake(r)
    assert result.outcome == "HUMAN" and result.reason == "bypass:ETHAN_NEED_HUMAN_NOW", result
    bypasses = [e for e in orch.decision_log() if e["kind"] == "bypass"]
    assert len(bypasses) == 1 and bypasses[0]["agent"] == "ETHAN", bypasses
    print("  ok: bypass — ETHAN's need-a-human-now skips the gate but is logged")


def test_bypass_critical_malfunction():
    orch = make_orchestrator(AlwaysNominal(), AlwaysNominal())
    r = report(agent="GRACIE", bypass=BypassReason.CRITICAL_MALFUNCTION)
    result = orch.intake(r)
    assert result.outcome == "HUMAN" and result.reason == "bypass:CRITICAL_MALFUNCTION", result
    print("  ok: bypass — a critical malfunction from any agent skips the gate too")


# --- logging: timestamp + originating agent on every entry -------------------

def test_every_log_entry_has_timestamp_and_agent():
    orch = make_orchestrator(AlwaysViolated(), AlwaysViolated())
    orch.intake(report(agent="GRACIE"))
    log = orch.decision_log()
    assert log, "expected at least one log entry"
    for entry in log:
        assert "timestamp" in entry and isinstance(entry["timestamp"], int)
        assert entry["agent"] == "GRACIE"
    print("  ok: logging — every decision entry carries a timestamp and originating agent")


def main():
    tests = [
        test_step3_intake_routes_through_triage_and_decide,
        test_step4_triage_classification,
        test_step5_decide_outcomes,
        test_step6_rerun_stable_result_escalates,
        test_step6_rerun_differs_then_stabilizes,
        test_step6_rerun_keeps_differing_escalates_regardless,
        test_step7_all_clear_releases,
        test_step8_any_dissent_goes_to_human,
        test_step9_process_count_floor,
        test_step9_timeout_floor,
        test_bypass_ethan_need_human_now,
        test_bypass_critical_malfunction,
        test_every_log_entry_has_timestamp_and_agent,
    ]
    for test in tests:
        test()
    print("All EscalationOrchestrator checks passed.")


if __name__ == "__main__":
    main()
