# sim/standard_release.py
# Added 2026-11-09 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Fault-clearing job, part B (Ccode update.txt, "JAY -- DESIGN
DECIDED"): standard release for MAJOR/NON_URGENT faults (SPEC.md's
Fault lifecycle, "Standard release (agent-resolved faults)" --
"Agent latches its flag, reports to EDEN, EDEN acts and confirms,
then the originating agent releases its own latch and logs"). BOOM
faults are explicitly out of scope here -- they keep sim/human_
signoff.py's existing four-way machinery, narrowed to boom only in
the same round this file was added.

SIM-ONLY STAND-IN, lives here not in agents/ -- same discipline as
sim/human_signoff.py and sim/expected_cause_confirmation.py: never
touches GracieAgent/EdenAgent beyond calling what they already
expose (gracie._last_readings, gracie.clear_fault(), eden.
fault_class_table, eden.confirm_settled() -- all already public).

Jay's 5-step design, as built:
  1. Readings back inside normal AND staying there for a settle time.
     "Normal" here means the channel is not currently within any
     REAL, live planted fault's window -- same ground-truth check
     sim/human_signoff.py already uses for its own HUMAN party, not
     re-derived. The settle clock only starts once that's true, and
     resets immediately if the fault goes live again.
  2. GRACIE asks EDEN; EDEN checks the readings herself and confirms
     -- eden.confirm_settled(channel, value), her own independent
     level-bounds check (agents/eden.py).
  3. Confirmed -> GRACIE releases her own latch (clear_fault) and
     logs it (this class's own question_log).
  4. Boom faults need a human too -- not this file's job, see above.
  5. Never released while the fault is still live -- checked every
     tick, not just once.

settle_time_seconds is a required constructor parameter, not a
ChannelRule field (same reasoning as sim/expected_cause_confirmation.
py's confirm_window_seconds -- GRACIE/EDEN's own ChannelRule is
shared by every caller in the whole codebase; only this sim-only
class needs this value). Sim's own placeholder: STILLNESS_WINDOW_
SECONDS (sim/blueprint.py) -- Stillness is GRACIE's slowest sense, so
one Stillness window's worth of continuous normal readings is a
reasoned floor for "genuinely settled", not a number invented fresh
(same reuse already used for the sim scorer's own grace constant).
"""
from agents.escalation_orchestrator import FaultClass


class StandardRelease:
    def __init__(self, gracie, eden, faults, settle_time_seconds):
        self.gracie = gracie
        self.eden = eden
        self.faults = faults
        self.settle_time_seconds = settle_time_seconds
        self._settled_since = {}  # channel -> second_offset the channel first looked settled
        self._question_log = []

    def question_log(self):
        """Every ask/outcome, in order -- read-only copy, same
        convention as the other sim-only trackers this round."""
        return list(self._question_log)

    def _channel_is_within_an_active_fault(self, channel, second_offset):
        """Identical check to sim/human_signoff.py's own -- not
        shared/imported, each sim-only tracker stays self-contained,
        same precedent as this round's other new files."""
        for f in self.faults:
            if channel in f["channel"].split(",") and f["start_s"] <= second_offset < f["end_s"]:
                return True
        return False

    def _log(self, channel, outcome, second_offset):
        self._question_log.append({"second_offset": second_offset, "channel": channel, "outcome": outcome})

    def tick(self, second_offset):
        """Call once per cycle, after GRACIE has processed this
        cycle's readings (same ordering as every other sim-only
        tracker this round)."""
        for channel, last in list(self.gracie._last_readings.items()):
            if last["severity"] == "NOMINAL":
                self._settled_since.pop(channel, None)
                continue  # nothing latched -- nothing to release

            sense = last.get("causing_sense")
            fault_class = self.eden.fault_class_table.get(channel, {}).get(sense) if sense is not None else None
            if fault_class is None:
                fault_class = FaultClass.MAJOR
            if fault_class == FaultClass.BOOM:
                self._settled_since.pop(channel, None)
                continue  # boom faults release via the four-way, not here

            if self._channel_is_within_an_active_fault(channel, second_offset):
                self._settled_since.pop(channel, None)  # step 5: never release while still live
                continue

            first_tick = channel not in self._settled_since
            if first_tick:
                self._settled_since[channel] = second_offset
                self._log(channel, "asked", second_offset)

            elapsed = second_offset - self._settled_since[channel]
            if elapsed < self.settle_time_seconds:
                continue

            if self.eden.confirm_settled(channel, last["value"]):
                self._log(channel, "released", second_offset)
                self.gracie.clear_fault(channel)
                self._settled_since.pop(channel, None)
