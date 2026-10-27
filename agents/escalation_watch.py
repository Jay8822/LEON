# agents/escalation_watch.py
# Added 2026-10-27 — Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""EscalationWatch — SPEC.md GRACIE section, "New crossing while
already latched ... that is reported as a fresh event in its own
right, through the normal escalation chain to the orchestrator."

STAND-IN, NOT THE FINAL ARCHITECTURE (Jay's explicit instruction,
Item 3b approval, point 2): this is a quick, narrow bridge so that
one specific SPEC.md requirement is actually satisfied today, the
same way agents/ghost_mode.py already bridges GRACIE's FAULT reports
to the orchestrator without GRACIE calling it directly. GRACIE still
has no idea the orchestrator exists; she only announces on
"chester/watch" (as she already does for jump/leash_settled/
warning_entered/warning_left). This harness listens for ONE specific
kind of that announcement and forwards it on, same reasoning as ghost
mode's own module docstring point 1: no real per-agent rule data
exists yet, so triage() is skipped and every match goes straight to
decide() with Severity.VIOLATED. When GRACIE is properly,
architecturally wired to the orchestrator, this file is replaced, not
extended.

Scope, deliberately narrow: ONLY "new_crossing_while_latched". Every
other chester/watch kind (jump, leash_settled, warning_entered,
warning_left) is explicitly NOT escalated here -- those already have
their own, different handling (GRACIE's own latching, CHESTER's
watch) and escalating them too would be a scope change nobody asked
for. Never touches GracieAgent or EscalationOrchestrator's own logic;
only reads the bus and calls the orchestrator's existing decide().

Same safety discipline as ghost_mode.py: every exception is caught and
logged here, never allowed to propagate -- this must never be able to
affect the real system."""

from core.bus import EventBus
from core.logger import setup_agent_logger
from agents.escalation_orchestrator import AgentReport, EscalationOrchestrator, Severity

_ESCALATED_KIND = "new_crossing_while_latched"


class EscalationWatch:
    """Watches GRACIE's "chester/watch" traffic for
    new_crossing_while_latched announcements specifically, and
    forwards each one to EscalationOrchestrator.decide() -- a
    stand-in bridge, not the final architecture (see module
    docstring)."""

    def __init__(self, bus: EventBus, orchestrator: EscalationOrchestrator):
        self.logger = setup_agent_logger("escalation_watch")
        self.bus = bus
        self.orchestrator = orchestrator
        self._forwarded_log = []
        self.bus.subscribe("chester/watch", self.on_watch)

    def forwarded_log(self):
        """Every report forwarded so far, same read-only-copy
        convention as EscalationOrchestrator.decision_log()."""
        return list(self._forwarded_log)

    def on_watch(self, payload):
        try:
            self._handle(payload)
        except Exception:
            self.logger.exception(
                f"escalation watch error, swallowed, no effect on real system: payload={payload}"
            )

    def _handle(self, payload):
        if payload.get("kind") != _ESCALATED_KIND:
            return  # every other chester/watch kind already has its own handling

        report = AgentReport(
            agent=payload.get("agent", "UNKNOWN"),
            value=payload,
            timestamp=payload.get("timestamp"),
        )
        # Known gap (see module docstring): no independent second check
        # on this report yet, same reasoning as ghost_mode.py's own
        # point 1 -- straight to decide().
        result = self.orchestrator.decide(report, Severity.VIOLATED)

        self._forwarded_log.append({
            "timestamp": payload.get("timestamp"),
            "channel": payload.get("channel"),
            "outcome": result.outcome,
            "reason": result.reason,
        })
        self.logger.info(
            "ESCALATED new_crossing_while_latched "
            f"channel={payload.get('channel')} outcome={result.outcome} reason={result.reason}"
        )
