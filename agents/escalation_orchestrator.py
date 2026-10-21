# agents/escalation_orchestrator.py
# Added 2026-08-01 — Jay Pratt + AI (Claude, Anthropic).
"""EscalationOrchestrator — SPEC.md "Orchestrator" (separate seventh
agent) + "Escalation chain (in order)".

Built against SPEC.md, draft Oct 2026. This is a new, self-contained
component — it does not call into, subscribe to, or modify GracieAgent,
EthanAgent, LunaeAgent, EdenAgent, HaliaAgent, SystemCoordinator, or
agents/orchestrator.py (SPEC.md is explicit that file is *not* this
component). Zero behaviour change to any existing agent in this pass.

Two things SPEC.md does not yet specify, resolved with explicit sign-off
rather than guessed:

1. No real per-agent thresholds exist anywhere in SPEC.md ("real numbers
   for every threshold" is listed as an open item pending hardware
   data). So rule-checking here is an injectable RuleSet interface, not
   real values — tests pass in fake example rules, explicitly not
   claimed as real spacecraft parameters. Wiring real thresholds in is
   future work.
2. The rerun instruction, ETHAN's "need a human now" signal, and the
   generic "critical malfunction" bypass trigger all require agent-side
   behaviour that doesn't exist on any current agent. This component is
   tested against synthetic AgentReport objects, not real agent output.
   Wiring the real mesh to actually produce these signals is separate
   future work.

The 9 steps from SPEC.md's "Escalation chain (in order)", and where each
lives below:

  1. Self-check            — agent-owned behaviour, not orchestrator logic.
                              No method here; nothing for this class to do.
  2. Load varies by phase  — descriptive, not actionable logic. No method.
  3. Unresolved -> orchestrator first   — intake()
     (bypass check happens first, since it must pre-empt everything else)
  4. Orchestrator checks (violated outright vs conflicting)   — triage()
  5. Orchestrator decides (EDEN vs rerun instruction)         — decide()
  6. Rerun logic (same twice / differs / keeps differing)     — record_rerun()
  7. Clear path (all-clear -> release)                        — consensus()
  8. Unclear path (dissent -> human)                          — consensus()
  9. Timeout / process-count floor                            — check_floor()

Interpretive calls made without a blocking question, documented here so
they're easy to correct:

- Step 4's "violated outright" requires BOTH the agent's own rules
  (held here via eden_rules, mirroring EDEN's copy) AND this
  orchestrator's own harder rules to agree it's violated — mirroring
  EDEN's own stated "both must align" validation principle one level
  earlier, rather than either rule alone being sufficient.
- Step 5's "decide" has no stated decision procedure for the ambiguous
  case. Implemented as: outright violation -> EDEN immediately;
  anything merely ambiguous -> rerun requested first (the rerun ladder
  is the very next thing SPEC.md describes, so this is the direct
  reading, not an invented branch).
- Step 6 "same result" means the same verdict/classification repeats
  (e.g. still AMBIGUOUS), not bit-identical sensor values — continuous
  readings essentially never repeat exactly.

Added 2026-10-21: SPEC.md's "Graceful degradation when EDEN does not
respond" (send_to_eden(), check_eden_silence()). One clock per fault,
starting at the knock (send_to_eden()); its length depends on fault
class (major faults get the shorter window; both lengths are required
constructor parameters with no defaults, per the same "no real numbers
yet" rule as everything else here). Unknown fault class is treated as
major (SPEC.md's explicit fallback). Two outcomes only — major
unresponsive -> HOLD + passed to a human; non-urgent unresponsive and
still live -> FLAGGED, craft keeps running. A non-urgent fault that
resolved on its own before its window elapsed produces no flag and no
hold, but is still logged (SPEC.md's core principle: "everything is
logged, regardless").

One more interpretive call, same spirit as the others above: if a
non-urgent fault's "still live" status is itself unknown (caller
passes `fault_still_live=None`), it's treated as still live — the same
cautious-default pattern as the unknown-fault-class rule, erring
toward flagging rather than silently standing down.

Added 2026-10-21 (second addition): SPEC.md's "Four-way sign-off" retest/
escalation ladder, "Hold course" state, and "After a manual override"
(start_signoff(), confirm(), use_override(), override_unused(),
check_after_override(), light_flag_tick()). All four parties (human,
orchestrator, originating agent, EDEN) must confirm, in any order, to
release. One gap once all four have weighed in triggers a retest for
everyone -- major faults get exactly one retest before a terminal
HOLD (flagged for investigation, no override path); non-urgent faults
get a second retest before a manual override becomes available. The
override is optional: if nobody uses it, the craft automatically
treats the fault as major except it goes to the new HOLD_COURSE state
(reduced speed, not a full stop) instead. Once the override *is* used,
the originating agent reruns its check; gone -> cleared, still present
-> flagged and then re-flagged ("light flag": queued, not an active
alert) on every self-check cycle until dealt with. The cycle interval
is another required, no-default constructor parameter, same "no real
numbers yet" rule as the rest of this file.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Protocol, Tuple

from core.logger import setup_agent_logger


class Severity(Enum):
    """Outcome of checking a report against a rule set (step 4)."""
    NOMINAL = "NOMINAL"
    AMBIGUOUS = "AMBIGUOUS"  # SPEC.md: "conflicting but not clearly a fault"
    VIOLATED = "VIOLATED"    # SPEC.md: "violated outright"


class Consensus(Enum):
    """Step 7/8: all-clear vs. dissent."""
    CLEAR = "CLEAR"
    UNCLEAR = "UNCLEAR"


class BypassReason(Enum):
    """"Orchestrator bypass": the two cases that skip the gate."""
    ETHAN_NEED_HUMAN_NOW = "ETHAN_NEED_HUMAN_NOW"
    CRITICAL_MALFUNCTION = "CRITICAL_MALFUNCTION"


class FaultClass(Enum):
    """SPEC.md "Fault classes" -- shared by the EDEN-silence degradation
    path and the four-way sign-off retest ladder."""
    MAJOR = "MAJOR"
    NON_URGENT = "NON_URGENT"


class SignOffParty(Enum):
    """SPEC.md "Four-way sign-off": who has to confirm."""
    HUMAN = "HUMAN"
    ORCHESTRATOR = "ORCHESTRATOR"
    ORIGINATING_AGENT = "ORIGINATING_AGENT"
    EDEN = "EDEN"


class RuleSet(Protocol):
    """A per-agent rule set. Deliberately just an interface — see the
    module docstring on why no real values are hardcoded here."""

    def check(self, report: "AgentReport") -> Severity: ...


@dataclass
class AgentReport:
    """Generic shape for "an agent reports something to the orchestrator".
    Not tied to any existing agent's real payload shape — see module
    docstring. `value` is whatever the (synthetic, for now) caller wants
    the rule set to evaluate."""
    agent: str
    value: object
    timestamp: int = field(default_factory=lambda: int(time.time()))
    bypass: Optional[BypassReason] = None


@dataclass
class ChainResult:
    """Where a report ended up, and why."""
    outcome: str  # "EDEN" | "RERUN_REQUESTED" | "HUMAN" | "CLEAR" |
                  # "HOLD" | "FLAGGED" | "CLEARED_NO_ACTION" |
                  # "RELEASE" | "RETEST_REQUESTED" | "OVERRIDE_AVAILABLE" |
                  # "OVERRIDE_USED" | "HOLD_COURSE"
    reason: str
    report: AgentReport


@dataclass
class PendingEdenKnock:
    """A report sent to EDEN (the "knock"), with a running clock. Created
    by send_to_eden(); passed back into check_eden_silence() once the
    caller wants to know whether EDEN has gone quiet."""
    report: AgentReport
    fault_class: FaultClass  # already resolved -- unknown becomes MAJOR
    started_at: float


@dataclass
class SignOffState:
    """Tracks one fault's progress through the four-way sign-off. Created
    by start_signoff(); passed back into confirm() and the rest of the
    sign-off/override methods. Not keyed internally by agent name, since
    a single agent could in principle have more than one fault awaiting
    sign-off at once -- the caller holds the reference, same pattern as
    PendingEdenKnock."""
    report: AgentReport
    fault_class: FaultClass
    confirmations: Dict[SignOffParty, bool] = field(default_factory=dict)
    retest_count: int = 0
    override_used: bool = False


class EscalationOrchestrator:
    def __init__(
        self,
        eden_rules: Dict[str, RuleSet],
        own_rules: Dict[str, RuleSet],
        major_fault_window_seconds: float,
        non_urgent_fault_window_seconds: float,
        light_flag_cycle_minutes: float,
        max_reruns: int = 3,
        process_count_floor: int = 5,
        timeout_seconds: float = 60.0,
    ):
        # major_fault_window_seconds / non_urgent_fault_window_seconds /
        # light_flag_cycle_minutes have no defaults on purpose -- SPEC.md
        # marks each "to be set from hardware data. No default value[s]."
        # Callers must supply real (or, for tests, clearly-labelled
        # fixture) numbers.
        self.logger = setup_agent_logger("escalation_orchestrator")
        self.eden_rules = eden_rules
        self.own_rules = own_rules
        self.major_fault_window_seconds = major_fault_window_seconds
        self.non_urgent_fault_window_seconds = non_urgent_fault_window_seconds
        self.light_flag_cycle_minutes = light_flag_cycle_minutes
        self.max_reruns = max_reruns
        self.process_count_floor = process_count_floor
        self.timeout_seconds = timeout_seconds
        self._rerun_history: Dict[str, List[Severity]] = {}
        self._decision_log: List[dict] = []

    # --- logging: every decision, bypass, and release -----------------
    def _log(self, kind: str, report: AgentReport, detail: str) -> dict:
        entry = {
            "timestamp": int(time.time()),
            "kind": kind,  # "decision" | "bypass" | "release"
            "agent": report.agent,
            "detail": detail,
        }
        self._decision_log.append(entry)
        self.logger.info(f"{kind.upper()} agent={report.agent} {detail}")
        return entry

    def decision_log(self) -> List[dict]:
        return list(self._decision_log)

    # --- step 3 + bypass check -------------------------------------------
    def intake(self, report: AgentReport) -> ChainResult:
        """Step 3: unresolved items go to the orchestrator first, not
        EDEN. The bypass check happens before anything else, since a
        bypass must pre-empt the normal gate entirely."""
        if report.bypass is not None:
            return self.bypass(report)
        severity = self.triage(report)
        return self.decide(report, severity)

    def bypass(self, report: AgentReport) -> ChainResult:
        """ETHAN's need-a-human-now and any critical malfunction skip
        the gate, straight to human interaction — but still leave a
        logged note to the orchestrator. The orchestrator never loses
        awareness; it only doesn't get to gate the fast path."""
        self._log("bypass", report, f"reason={report.bypass.value}")
        return ChainResult("HUMAN", f"bypass:{report.bypass.value}", report)

    # --- step 4: orchestrator checks --------------------------------------
    def triage(self, report: AgentReport) -> Severity:
        """Check against the agent's own rules (held here via eden_rules)
        and this orchestrator's own harder parameters. Both must agree
        for an outright violation or an outright all-clear; anything
        else is ambiguous."""
        agent_verdict = self.eden_rules[report.agent].check(report)
        own_verdict = self.own_rules[report.agent].check(report)
        if agent_verdict == Severity.VIOLATED and own_verdict == Severity.VIOLATED:
            return Severity.VIOLATED
        if agent_verdict == Severity.NOMINAL and own_verdict == Severity.NOMINAL:
            return Severity.NOMINAL
        return Severity.AMBIGUOUS

    # --- step 5: orchestrator decides --------------------------------------
    def decide(self, report: AgentReport, severity: Severity) -> ChainResult:
        """Violated outright -> straight to EDEN. Ambiguous -> rerun
        requested (step 6 is the ladder that follows). Nominal -> no
        escalation at all."""
        if severity == Severity.VIOLATED:
            self._log("decision", report, "VIOLATED -> EDEN")
            return ChainResult("EDEN", "violated_outright", report)
        if severity == Severity.NOMINAL:
            self._log("decision", report, "NOMINAL -> no escalation")
            return ChainResult("CLEAR", "nominal", report)
        # Seed the rerun history with this original ambiguous check, so
        # the first actual rerun is compared against *it* (SPEC.md: "the
        # agent reruns the test" implies check #1 is the original, check
        # #2 is the first rerun — "same result twice" means check #2
        # matches check #1, not that two reruns must happen first).
        self._rerun_history[report.agent] = [severity]
        self._log("decision", report, "AMBIGUOUS -> rerun requested")
        return ChainResult("RERUN_REQUESTED", "ambiguous", report)

    # --- step 6: rerun ladder ------------------------------------------------
    def record_rerun(self, report: AgentReport, severity: Severity) -> ChainResult:
        """Caller supplies each successive rerun's severity. Same result
        as the previous check -> raised to EDEN (stable, confirmed).
        Different -> rerun again. Keeps differing past max_reruns ->
        raised to EDEN regardless of parameters (instability itself is
        grounds for escalation). History is seeded by decide() with the
        original ambiguous check, so the first rerun compares against
        that, not just against other reruns."""
        history = self._rerun_history.setdefault(report.agent, [])
        history.append(severity)
        if len(history) >= 2 and history[-1] == history[-2]:
            self._log("decision", report, f"same result twice ({severity.value}) -> EDEN")
            self._rerun_history.pop(report.agent, None)
            return ChainResult("EDEN", "rerun_stable", report)
        if len(history) >= self.max_reruns:
            self._log("decision", report, "results kept differing -> EDEN regardless")
            self._rerun_history.pop(report.agent, None)
            return ChainResult("EDEN", "rerun_unstable", report)
        self._log("decision", report, f"result differs (check #{len(history)}) -> rerun again")
        return ChainResult("RERUN_REQUESTED", "rerun_differs", report)

    # --- step 7 / 8: consensus -----------------------------------------------
    def consensus(self, entries: List[Tuple[AgentReport, Consensus]]) -> ChainResult:
        """Step 7: every agent involved sends all-clear -> release,
        logged for each. Step 8: any one dissenting "unclear" -> human.
        Consensus is required to stand down; any dissent goes to a
        person."""
        if all(verdict == Consensus.CLEAR for _, verdict in entries):
            for report, _ in entries:
                self._log("release", report, "all-clear, latch released")
            return ChainResult("CLEAR", "consensus_clear", entries[0][0])
        dissenting_report, _ = next(
            (report, verdict) for report, verdict in entries if verdict == Consensus.UNCLEAR
        )
        self._log("decision", dissenting_report, "dissent -> human")
        return ChainResult("HUMAN", f"dissent:{dissenting_report.agent}", dissenting_report)

    # --- step 9: timeout / process-count floor --------------------------------
    def check_floor(
        self, report: AgentReport, process_count: int, elapsed_seconds: float
    ) -> Optional[ChainResult]:
        """True last resort. If conflict persists beyond the process-
        count floor or the time limit, raised for human interaction
        regardless of anything else — no infinite retry loops. Returns
        None if neither limit has been crossed yet."""
        if process_count > self.process_count_floor or elapsed_seconds > self.timeout_seconds:
            self._log(
                "decision",
                report,
                f"timeout/process floor hit (count={process_count}, "
                f"elapsed={elapsed_seconds:.1f}s) -> human",
            )
            return ChainResult("HUMAN", "timeout_floor", report)
        return None

    # --- graceful degradation when EDEN does not respond -----------------
    def send_to_eden(
        self, report: AgentReport, fault_class: Optional[FaultClass] = None
    ) -> PendingEdenKnock:
        """The knock. Starts this fault's clock. Unknown fault class is
        treated as major (SPEC.md's explicit fallback), not as a reason
        to fail or guess further."""
        resolved_class = fault_class if fault_class is not None else FaultClass.MAJOR
        if fault_class is None:
            self._log("decision", report, "fault class unknown -> treated as MAJOR")
        self._log(
            "decision", report, f"knock sent to EDEN (fault_class={resolved_class.value})"
        )
        return PendingEdenKnock(report=report, fault_class=resolved_class, started_at=time.time())

    def check_eden_silence(
        self,
        pending: PendingEdenKnock,
        elapsed_seconds: float,
        fault_still_live: Optional[bool] = None,
    ) -> Optional[ChainResult]:
        """Step: has EDEN gone quiet on this fault for longer than its
        window? Two outcomes only, by fault class — a major fault holds
        and is passed to a human; a non-urgent fault is flagged and the
        craft keeps running. A non-urgent fault that resolved on its own
        before the window elapsed produces neither, but is still logged
        (SPEC.md's core principle: everything is logged, regardless).
        Returns None if the window hasn't elapsed yet."""
        report = pending.report
        if pending.fault_class == FaultClass.MAJOR:
            window = self.major_fault_window_seconds
        else:
            window = self.non_urgent_fault_window_seconds

        if elapsed_seconds < window:
            return None

        if pending.fault_class == FaultClass.MAJOR:
            self._log(
                "decision", report,
                f"EDEN unresponsive beyond major window ({window}s) -> HOLD, passed to human",
            )
            return ChainResult("HOLD", "major_unresponsive_passed", report)

        # Non-urgent. Unknown liveness is treated as still live -- same
        # cautious-default pattern as the unknown-fault-class rule above.
        still_live = fault_still_live if fault_still_live is not None else True
        if still_live:
            self._log(
                "decision", report,
                f"EDEN unresponsive beyond non-urgent window ({window}s), "
                "fault still live -> FLAGGED, craft keeps running",
            )
            return ChainResult("FLAGGED", "non_urgent_unresponsive_flagged", report)

        self._log(
            "decision", report,
            f"EDEN unresponsive beyond non-urgent window ({window}s), "
            "but fault cleared on its own -> no flag, no hold, logged only",
        )
        return ChainResult("CLEARED_NO_ACTION", "non_urgent_resolved_on_own", report)

    # --- four-way sign-off -------------------------------------------------
    def start_signoff(self, report: AgentReport, fault_class: FaultClass) -> SignOffState:
        """Begin tracking the four-way sign-off for one fault."""
        self._log("decision", report, f"four-way sign-off started (fault_class={fault_class.value})")
        return SignOffState(report=report, fault_class=fault_class)

    def confirm(
        self, state: SignOffState, party: SignOffParty, confirmed: bool
    ) -> Optional[ChainResult]:
        """One party confirms (or doesn't). Order doesn't matter. Once
        all four have weighed in: unanimous "yes" releases; any "no"
        triggers the retest ladder (_handle_signoff_gap). Returns None
        while parties are still pending, same convention as
        check_eden_silence()/check_floor()."""
        state.confirmations[party] = confirmed
        self._log("decision", state.report, f"sign-off: {party.value} confirmed={confirmed}")

        if len(state.confirmations) < len(SignOffParty):
            return None  # still waiting on at least one party

        if all(state.confirmations.values()):
            self._log("release", state.report, "four-way sign-off complete, latch released")
            return ChainResult("RELEASE", "four_way_signoff_complete", state.report)

        return self._handle_signoff_gap(state)

    def _handle_signoff_gap(self, state: SignOffState) -> ChainResult:
        """Not all four agreed. Major faults get one retest before a
        terminal HOLD (no override path). Non-urgent faults get a
        second retest before a manual override becomes available."""
        required_retests = 1 if state.fault_class == FaultClass.MAJOR else 2

        if state.retest_count < required_retests:
            state.retest_count += 1
            state.confirmations.clear()
            self._log(
                "decision", state.report,
                f"sign-off gap -> retest #{state.retest_count} of {required_retests}",
            )
            return ChainResult("RETEST_REQUESTED", "signoff_gap", state.report)

        if state.fault_class == FaultClass.MAJOR:
            self._log(
                "decision", state.report,
                "still not confirmed after retest -> HOLD, flagged for further investigation",
            )
            return ChainResult("HOLD", "major_signoff_failed", state.report)

        self._log(
            "decision", state.report,
            "still not confirmed after double retest -> manual override available",
        )
        return ChainResult("OVERRIDE_AVAILABLE", "non_urgent_signoff_failed", state.report)

    def use_override(self, state: SignOffState) -> ChainResult:
        """A human uses the non-urgent manual override."""
        state.override_used = True
        self._log("decision", state.report, "manual override used")
        return ChainResult("OVERRIDE_USED", "non_urgent_override_used", state.report)

    def override_unused(self, state: SignOffState) -> ChainResult:
        """Nobody used the override. The craft automatically treats the
        fault as major, except it holds course at reduced speed instead
        of a full stop."""
        self._log(
            "decision", state.report,
            "override not used -> HOLD_COURSE, treated as major (reduced speed, not full stop)",
        )
        return ChainResult("HOLD_COURSE", "non_urgent_override_unused", state.report)

    def check_after_override(
        self, state: SignOffState, fault_still_present: bool
    ) -> ChainResult:
        """SPEC.md "After a manual override": the originating agent
        reruns its test, to check the fault isn't spreading or
        creeping. Gone -> cleared. Still present -> logged for a
        person, and the light-flag cycle begins (see light_flag_tick())."""
        if not fault_still_present:
            self._log("decision", state.report, "post-override rerun: fault gone -> cleared")
            return ChainResult("CLEARED_NO_ACTION", "override_rerun_cleared", state.report)
        self._log(
            "decision", state.report,
            "post-override rerun: fault still present -> logged for a person, "
            "light-flag cycle begins",
        )
        return ChainResult("FLAGGED", "override_rerun_fault_persists", state.report)

    def light_flag_tick(self, state: SignOffState) -> ChainResult:
        """One tick of the recurring light-flag cycle. Caller invokes
        this once per self-check cycle (length: light_flag_cycle_minutes)
        while the fault remains undealt-with. Each call logs again --
        "light flag" means flagged, repeated every cycle, not an active
        alert, so repetition is the entire point rather than something
        to suppress on repeat calls."""
        self._log(
            "decision", state.report,
            f"light flag (recurring every {self.light_flag_cycle_minutes}min, not an active alert)",
        )
        return ChainResult("FLAGGED", "light_flag_cycle", state.report)
