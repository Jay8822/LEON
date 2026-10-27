# sim/human_signoff.py
# Added 2026-10-27 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Simulated human sign-off for the simulated LEON craft (Item 3b,
Jay's approved change 6). SPEC.md's Sign-off rules need a human in the
loop before a fault-hold releases; this sim has none, so without
something standing in for one, every latch (real or falsely
triggered) persists for the rest of this one continuous 6-hour run --
exactly why the first round found EDEN in SAFE_MODE for 20,766/21,600
samples (96%) of it, regardless of what the plan did for any
individual channel.

SIM-ONLY STAND-IN, lives here, not in agents/ -- never touches
GracieAgent's own logic beyond calling her existing clear_fault
(channel), the same method a real human-confirmed release already
uses, and drives EscalationOrchestrator's real sign-off state machine
(start_signoff/confirm) rather than bypassing it -- "exercise the full
chain" (the original approved plan's point 7) already named sign-off
as in scope; the first round never actually exercised it (only
decide(), via ghost_mode.py/escalation_watch.py).

MECHANICS: tracks, per channel, how long its OWN FAULT latch has been
continuously active. The other three sign-off parties (ORCHESTRATOR,
ORIGINATING_AGENT, EDEN) have no independent check of their own yet --
same documented, named gap as agents/ghost_mode.py's own module
docstring, point 1 -- so they simply confirm whatever GRACIE already
reported; only HUMAN is genuinely delayed. Once a channel's latch has
been active for at least RESPONSE_DELAY_SECONDS (a sim-only
parameter, not a real spacecraft number -- reused from this sim's own
CHESTER_REFRESH_PERIOD_SECONDS scale for consistency, not invented
fresh), "the human" checks sim/fault_injection.py's own known truth
for that exact second: is this channel currently inside one of the
planted faults' own window? If yes, the human correctly recognises
it's still live and does NOT confirm release (one sign-off retest
follows automatically, per EscalationOrchestrator's own major-fault
rule, then HOLD -- harmless; the next tick where the fault genuinely
isn't live any more simply overwrites every party's confirmation and
releases, no special-case handling needed). If no (a false alarm, or
a real fault whose window has already closed), the human confirms,
all four agree, and clear_fault(channel) actually fires.

Jay's NOTE for a later round, not built here: a variant where the
simulated human sometimes answers wrong, to test whether the four-way
sign-off itself catches human error ("humans can miss things")."""

from agents.escalation_orchestrator import AgentReport, EscalationOrchestrator, FaultClass, SignOffParty


class HumanSignoff:
    def __init__(self, gracie, orchestrator: EscalationOrchestrator, faults, response_delay_seconds):
        self.gracie = gracie
        self.orchestrator = orchestrator
        self.faults = faults
        self.response_delay_seconds = response_delay_seconds
        self._fault_since = {}       # channel -> second_offset the latch started
        self._signoff_states = {}    # channel -> SignOffState, once sign-off has begun

    def _channel_is_within_an_active_fault(self, channel, second_offset):
        for f in self.faults:
            if channel in f["channel"].split(",") and f["start_s"] <= second_offset < f["end_s"]:
                return True
        return False

    def tick(self, second_offset):
        """Call once per cycle, after GRACIE has processed this
        cycle's readings. Releases any channel whose FAULT latch has
        run past the response delay and is not currently inside a
        real, still-live planted fault."""
        for channel, last in list(self.gracie._last_readings.items()):
            if last["severity"] != "FAULT":
                self._fault_since.pop(channel, None)
                self._signoff_states.pop(channel, None)
                continue

            if channel not in self._fault_since:
                self._fault_since[channel] = second_offset

            if channel not in self._signoff_states:
                report = AgentReport(agent="GRACIE", value={"channel": channel}, timestamp=second_offset)
                self._signoff_states[channel] = self.orchestrator.start_signoff(report, FaultClass.MAJOR)

            elapsed = second_offset - self._fault_since[channel]
            if elapsed < self.response_delay_seconds:
                continue

            state = self._signoff_states[channel]
            # Re-confirmed every tick past the delay, not just once --
            # a prior retest may have cleared these, and re-sending an
            # unchanged "True" is harmless either way (confirm() just
            # overwrites, "order doesn't matter").
            self.orchestrator.confirm(state, SignOffParty.ORCHESTRATOR, True)
            self.orchestrator.confirm(state, SignOffParty.ORIGINATING_AGENT, True)
            self.orchestrator.confirm(state, SignOffParty.EDEN, True)

            still_live = self._channel_is_within_an_active_fault(channel, second_offset)
            result = self.orchestrator.confirm(state, SignOffParty.HUMAN, not still_live)
            if result is not None and result.outcome == "RELEASE":
                self.gracie.clear_fault(channel)
                self._fault_since.pop(channel, None)
                self._signoff_states.pop(channel, None)
