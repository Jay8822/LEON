# agents/ghost_mode.py
# Added 2026-10-23 — Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""GhostModeHarness — SPEC.md "Wiring plan and ghost mode," GRACIE only.

Task 3 of HANDOVER.md's work queue: wire GRACIE's FAULT reports into
EscalationOrchestrator without changing what currently controls the
ship. "The old wiring" — EdenAgent — keeps full control. This harness
only watches the same real "telemetry/health" traffic EDEN already
reacts to, asks the orchestrator what it would have done, and logs the
comparison. It never publishes to the bus, never calls a command
method on any agent, and never changes GracieAgent, EdenAgent, or
EscalationOrchestrator.

Interpretive calls made this pass, agreed with Jay before building
(see "Ccode update.txt" history for task 3):

1. No independent second check on GRACIE's faults yet. SPEC.md's
   normal path (triage()) requires two rule sets — the agent's own and
   the orchestrator's own harder one — to independently agree before
   calling something VIOLATED. No real threshold data exists for
   either side of that check (SPEC.md's own open item), and GRACIE's
   own wiring already resolves "only faults go to the orchestrator" —
   by the time a report reaches this harness, GRACIE has already made
   the only call that matters. So triage() is skipped here: every
   GRACIE FAULT goes straight to decide() with Severity.VIOLATED. This
   is a known, named gap, not a quiet shortcut — the orchestrator is
   not yet doing real independent validation on GRACIE's faults, and
   won't be until real rule data exists.

2. "The old wiring" means EdenAgent's reaction specifically — the one
   thing that currently *acts* on a GRACIE fault (commanding
   SAFE_MODE). This harness reads `eden.status` right after dispatching
   to the orchestrator, relying on main.py subscribing this harness to
   "telemetry/health" *after* eden.on_health_event, so EDEN has already
   updated its status for this exact event by the time this handler
   runs. See test_ghost_mode_depends_on_subscription_order_after_eden
   in ghost_mode_test.py — it exists specifically to catch it if that
   ordering ever changes.

3. GRACIE has no fault-class concept (major/non-urgent) at all today —
   only NOMINAL/WARNING/FAULT. Since GracieAgent isn't being changed,
   every GRACIE fault is "unknown class" by construction, which
   SPEC.md's own fallback already resolves (unknown means major). This
   harness doesn't classify anything itself; it only logs that the
   question doesn't yet apply to GRACIE.

4. No raw readings in this harness's own log. At the time this was
   built, GracieAgent.report_health() only ever published
   {"system_health", "source", "timestamp"} to "telemetry/health", so
   there was nothing to log beyond health-state. GRACIE's later
   any-sensor upgrade (agents/gracie.py) added a "readings" key with
   her actual per-channel values -- this harness still doesn't read
   or log it, by original design choice now, not for lack of data.
   Nothing here needed to change for that upgrade: see
   test_real_upgraded_gracie_payload_still_triggers_ghost_mode in
   ghost_mode_test.py.

5. Scope is deliberately narrow: one FAULT in, one orchestrator verdict
   out (decide()'s result), logged against EDEN's real action. No
   rerun ladder, no EDEN-silence degradation, no sign-off — none of
   that machinery has anything to attach to yet (GRACIE has no rerun
   trigger, and no sign-off confirmations exist anywhere in the mesh).

Safety requirement (Jay, task 3 approval): ghost mode must never be
able to affect the real system. Every exception, bad payload, or
logging failure inside this harness is caught and logged here, never
allowed to propagate — not relying solely on EventBus's own per-handler
isolation (core/bus.py), since that isolation is a property of a
different file and this harness's own safety should not be implicit.
"""

from core.bus import EventBus
from core.logger import setup_agent_logger
from agents.escalation_orchestrator import AgentReport, EscalationOrchestrator, Severity


class GhostModeHarness:
    """Watches GRACIE's real "telemetry/health" traffic and logs what
    EscalationOrchestrator would have decided, alongside what EDEN
    actually did, without controlling anything."""

    def __init__(self, bus: EventBus, eden, orchestrator: EscalationOrchestrator):
        self.logger = setup_agent_logger("ghost_mode")
        self.bus = bus
        self.eden = eden
        self.orchestrator = orchestrator
        self._comparison_log = []
        self.bus.subscribe("telemetry/health", self.on_health_event)

    def comparison_log(self):
        """Every FAULT comparison made so far, same read-only-copy
        convention as EscalationOrchestrator.decision_log()."""
        return list(self._comparison_log)

    def on_health_event(self, payload):
        try:
            self._handle(payload)
        except Exception:
            # Ghost mode must never take the real system down with it.
            self.logger.exception(
                f"ghost mode harness error, swallowed, no effect on real system: payload={payload}"
            )

    def _handle(self, payload):
        health = payload.get("system_health")
        if health != "FAULT":
            # "GRACIE fixes and logs her own warnings. Only faults go
            # to the orchestrator." NOMINAL/WARNING stay local to
            # GRACIE, exactly as today — ghost mode has nothing to do.
            return

        source = payload.get("source", "UNKNOWN")
        report = AgentReport(agent=source, value=payload, timestamp=payload.get("timestamp"))

        # Known gap (see module docstring, point 1): no independent
        # second check on GRACIE's faults yet. Treated as already-
        # decided, straight to decide().
        ghost_result = self.orchestrator.decide(report, Severity.VIOLATED)

        old_wiring_status = self.eden.status
        old_wiring_acted = old_wiring_status == "SAFE_MODE"
        ghost_would_escalate = ghost_result.outcome == "EDEN"
        agree = old_wiring_acted == ghost_would_escalate

        self._comparison_log.append({
            "timestamp": payload.get("timestamp"),
            "source": source,
            "health": health,
            "ghost_outcome": ghost_result.outcome,
            "ghost_reason": ghost_result.reason,
            "old_wiring_status": old_wiring_status,
            "agree": agree,
        })

        self.logger.info(
            "GHOST COMPARISON "
            f"source={source} health={health} "
            f"ghost_outcome={ghost_result.outcome} ghost_reason={ghost_result.reason} "
            f"old_wiring_status={old_wiring_status} "
            f"agree={agree}"
        )
        if not agree:
            self.logger.warning(
                "GHOST DISAGREEMENT "
                f"source={source} ghost_outcome={ghost_result.outcome} "
                f"old_wiring_status={old_wiring_status}"
            )
