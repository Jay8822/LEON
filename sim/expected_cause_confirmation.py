# sim/expected_cause_confirmation.py
# Added 2026-11-09 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""EDEN expected-boom-readings job, part A (Ccode update.txt, "JAY --
DESIGN DECIDED": "When GRACIE excuses a reading on a boom channel...
EDEN asks the correct agent... to confirm the cause really is
happening. Confirmed -> LOG, no safe mode. Not confirmed, or no
answer within its window -> RAISE it as a real boom fault.").

SIM-ONLY STAND-IN, lives here not in agents/ -- same discipline as
sim/human_signoff.py: never touches GracieAgent/EdenAgent beyond
calling what they already expose (reading gracie._last_readings,
calling eden.react_to_fault_class() -- both already public). EDEN
herself does no asking or waiting (agents/eden.py's own _classify()
just stays quiet on an excused boom channel); this class is the thing
doing the asking, ticked once per cycle, same pattern as HumanSignoff.

"The owning agent" is never actually interrogated as a live agent --
there is no real ETHAN/LUNAE state in this codebase that knows
whether a burn is genuinely commanded (agents/ethan_ai.py is a
command-and-status-echo stub, same for agents/lunae.py). Instead this
checks sim/craft.py's own EVENT_SCHEDULE ground truth directly, same
pattern as HumanSignoff checking sim/fault_injection.py's faults for
its own confirmation. This stands in for "the owning agent answers
truthfully" -- a new, OPEN assumption (ASSUMPTIONS.md A85) -- not
tested this round, same deferral as HumanSignoff's own named note
about a sometimes-wrong simulated human for a later round.

A channel is tracked here at all based on GRACIE's `excused` field
(true whenever this reading matched an expected cause this cycle,
REGARDLESS of whether an owner is known) -- not `excused_by`, which
can legitimately be None while `excused` is still True (sim/
blueprint.py's EVENT_OWNERS states None for some event kinds). Using
excused_by alone would make "excused with no owner" indistinguishable
from "never excused at all", and this round's own first draft did
exactly that -- caught before it shipped, not after.

TWO DISTINCT ways to end up "not confirmed", both raising (Jay's own
wording keeps them separate, so this does too):
  - UNKNOWN OWNER (`excused_by` is None -- GRACIE's own report, no
    re-derivation needed here): nobody to ask at all. Raises
    IMMEDIATELY -- this is a static property of the excusal itself,
    not a timing question. "Unknown owner = not confirmed = raise."
  - OWNER KNOWN, GROUND TRUTH DISAGREES: `excused_by` names a real
    owner, but no currently-active event matches it (checked against
    sim/craft.py's own EVENT_SCHEDULE via sim/blueprint.py's
    EVENT_OWNERS). This starts a clock; if the ground truth hasn't
    confirmed it before confirm_window_seconds elapses, raises.
In THIS round's real sim run, GRACIE's own excusal and this
independent ground-truth check read the EXACT same EVENT_SCHEDULE, so
confirmation here always matches immediately -- neither "not
confirmed" path fires naturally. Both are proven by unit test instead
(fabricated scenarios the real run doesn't produce), stated plainly,
not glossed over.

Every question and answer is logged (Jay's own rule) -- once per
transition (asked / confirmed / raised), not every tick a channel
stays excused, same "log the transition, not the steady state"
convention agents/gracie.py's own _announce_warning_transition uses.
"""

from agents.escalation_orchestrator import FaultClass


class ExpectedCauseConfirmation:
    def __init__(self, gracie, eden, events, event_owners, confirm_window_seconds):
        self.gracie = gracie
        self.eden = eden
        self.events = events
        self.event_owners = event_owners
        self.confirm_window_seconds = confirm_window_seconds
        self._pending_since = {}  # channel -> second_offset first seen excused+boom, awaiting confirmation
        self._question_log = []

    def question_log(self):
        """Every question and its answer, in order -- read-only copy,
        same convention as EscalationOrchestrator.decision_log() and
        GhostModeHarness.comparison_log()."""
        return list(self._question_log)

    def _ground_truth_confirms(self, channel, owner, second_offset):
        """True iff some event currently active for this channel is
        owned (sim/blueprint.py's EVENT_OWNERS) by exactly `owner` --
        the independent ground-truth check standing in for "the
        owning agent answers truthfully" (ASSUMPTIONS.md A85)."""
        for ev in self.events:
            if not (ev["start_s"] <= second_offset < ev["end_s"]):
                continue
            if channel not in ev["affected_channels"]:
                continue
            if self.event_owners.get(ev["kind"]) == owner:
                return True
        return False

    def _log(self, channel, outcome, owner, second_offset):
        entry = {"second_offset": second_offset, "channel": channel, "owner": owner, "outcome": outcome}
        self._question_log.append(entry)
        return entry

    def tick(self, second_offset):
        """Call once per cycle, after GRACIE has processed this
        cycle's readings (same ordering as HumanSignoff.tick()).
        Channels not currently BOOM-excused are untracked -- entering
        and leaving the excused state is itself a transition, same as
        any other sense's own edge-triggering in this codebase."""
        for channel, last in list(self.gracie._last_readings.items()):
            sense = last.get("causing_sense")
            fault_class = self.eden.fault_class_table.get(channel, {}).get(sense) if sense is not None else None
            is_boom_excused = bool(last.get("excused")) and fault_class == FaultClass.BOOM

            if not is_boom_excused:
                self._pending_since.pop(channel, None)
                continue

            owner = last.get("excused_by")  # GRACIE's own report already carries this -- no re-derivation needed
            first_tick = channel not in self._pending_since
            if first_tick:
                self._pending_since[channel] = second_offset
                self._log(channel, "asked", owner, second_offset)

            if owner is None:
                # Excused, but no owner to ask at all -- a static
                # property of the excusal itself (sim/blueprint.py's
                # EVENT_OWNERS states None for this event kind), not
                # a timing question. Raises immediately, no window.
                # Jay: "unknown owner = not confirmed = raise."
                self._log(channel, "raised_no_owner", owner, second_offset)
                self.eden.react_to_fault_class(FaultClass.BOOM, reason="UNCONFIRMED")
                self._pending_since.pop(channel, None)
                continue

            if self._ground_truth_confirms(channel, owner, second_offset):
                self._log(channel, "confirmed", owner, second_offset)
                self._pending_since.pop(channel, None)
                continue

            elapsed = second_offset - self._pending_since[channel]
            if elapsed >= self.confirm_window_seconds:
                self._log(channel, "raised_timeout", owner, second_offset)
                self.eden.react_to_fault_class(FaultClass.BOOM, reason="UNCONFIRMED")
                self._pending_since.pop(channel, None)
