# agents/eden.py
# Updated 2026-10-28 — fault-class-aware reaction, replacing the legacy
# "any FAULT -> SAFE_MODE" shortcut (Item C). Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Item C (28 October 2026): replaces on_health_event's old `if
health == "FAULT": SAFE_MODE` with a reaction based on the actual
fault's class (SPEC.md's GRACIE "Fault class" bullet and "EDEN"
section, applied exactly as corrected and approved -- see
Ccode update.txt, "JAY'S ANSWERS TO ITEM C"):

- NON_URGENT: flagged and logged only -- `status` stays "MONITORING",
  no command published, the craft keeps running (SPEC.md's Fault
  lifecycle section already said this; the bug was that the code
  never implemented it).
- MAJOR: `status = "HOLD"`, commands LUNAE via the existing
  NAV_ADJUST/"cmd/nav" path (same CommandPacket shape EDEN already
  uses for SAFE_MODE, just a different command/topic -- confirmed
  working, not new plumbing: see agents/lunae.py's on_nav_command).
- BOOM: `status = "SAFE_MODE"`, same "cmd/propulsion" SAFE_MODE
  command as before -- now reserved for boom faults only. EDEN's job
  here is only to issue that command; the four-way, no-retest-ladder
  sign-off BOOM also requires (SPEC.md's Sign-off rules) is a
  SEPARATE mechanism (`agents/escalation_orchestrator.py`, already
  built, "not wired into agents" per its own status line) -- not
  driven from inside this file, which is deliberately not a bigger
  architectural change than Jay asked for this round.
- Unknown (no table entry for the reporting channel+sense): MAJOR,
  per SPEC.md's "if the fault class is unknown, treat it as major" --
  same rule GRACIE's own rule book follows.

EDEN's own fault-class table covers GRACIE's real table only, this
round (point 2 of Jay's approval) -- no fabricated rule sets for
ETHAN, LUNAE or HALIA, none of which have a real one yet.

NOT done here, a deliberate scope boundary, not an oversight:
validating a report against her OWN tighter tolerances (SPEC.md:
"Validates each report against the reporting agent's rules AND her
own parameters") -- Jay left this as a choice between bundling it in
or making it its own round; flagged to him as its own, separate round
(a genuinely different mechanism, with its own real design
questions), not built here.
"""

import time
from typing import Dict, Optional

from core.bus import EventBus
from core.logger import setup_agent_logger
from core.schemas import CommandPacket
from agents.escalation_orchestrator import FaultClass

# Hold -> Hold course -> Safe mode, mildest to most serious (SPEC.md
# "Ship safe states") -- used to pick the WORST class among every
# channel currently at WARNING/FAULT in one report, not just whichever
# channel happens to iterate first.
_FAULT_CLASS_RANK = {FaultClass.NON_URGENT: 0, FaultClass.MAJOR: 1, FaultClass.BOOM: 2}


class EdenAgent:
    def __init__(self, bus: EventBus, fault_class_table: Optional[Dict[str, Dict[str, FaultClass]]] = None):
        self.logger = setup_agent_logger("eden")
        self.bus = bus
        self.bus.subscribe("eden/command", self.on_command)
        self.status = "IDLE"
        # channel -> sense ("level"/"leash_soft"/"leash_hard"/
        # "stillness", matching agents/gracie.py's own causing_sense
        # vocabulary directly, no translation needed) -> FaultClass.
        # Empty by default so every existing caller's unqualified
        # EdenAgent(bus) keeps working -- an empty/missing lookup
        # always falls back to MAJOR, never NON_URGENT or BOOM.
        self.fault_class_table = fault_class_table or {}

    def send_status_update(self):
        payload = {
            "status": self.status,
            "timestamp": int(time.time())
        }
        self.logger.info(f"Status update: {payload}")  # <-- Logging instead of print!
        self.bus.publish("eden/status_update", payload)

    def on_command(self, payload):
        command = payload.get("command")
        self.logger.info(f"Received command: {command} with payload {payload}")
        if command == "run_diagnostics":
            self.logger.info("Running diagnostics")
            self.status = "DIAGNOSTIC"
            self.send_status_update()
            # Simulate diagnostic done
            self.status = "NOMINAL"
            self.send_status_update()
        elif command == "set_mode":
            mode = payload.get("parameters", {}).get("mode")
            if mode:
                self.status = mode
                self.logger.info(f"Mode set to: {mode}")
                self.send_status_update()

    def _classify(self, payload) -> FaultClass:
        """The WORST fault class among every channel in this report
        currently at WARNING or FAULT -- not just the first one found,
        since more than one channel can be non-NOMINAL in the same
        report. Falls back to MAJOR wherever a channel's causing_sense
        has no entry in her table (SPEC.md: unknown means major)."""
        worst = None
        for channel, info in payload.get("readings", {}).items():
            if info.get("severity") not in ("WARNING", "FAULT"):
                continue
            sense = info.get("causing_sense")
            fc = self.fault_class_table.get(channel, {}).get(sense) if sense is not None else None
            if fc is None:
                fc = FaultClass.MAJOR
            if worst is None or _FAULT_CLASS_RANK[fc] > _FAULT_CLASS_RANK[worst]:
                worst = fc
        return worst if worst is not None else FaultClass.MAJOR

    def on_health_event(self, payload):
        health = payload.get("system_health")
        self.logger.info(f"Health event received: {health}")
        if health not in ("WARNING", "FAULT"):
            self.status = "MONITORING"
            self.send_status_update()
            return

        fault_class = self._classify(payload)
        if fault_class == FaultClass.NON_URGENT:
            self.logger.info(f"Non-urgent fault -- flagged and logged, craft keeps running (health={health})")
            self.status = "MONITORING"
        elif fault_class == FaultClass.BOOM:
            self.logger.error("EDEN detected a BOOM fault! Sending SAFE_MODE command...")
            self.status = "SAFE_MODE"
            cmd = CommandPacket(command="SAFE_MODE", mode=None, reason="GRACIE_BOOM")
            self.bus.publish("cmd/propulsion", cmd.__dict__)
        else:  # MAJOR, including "unknown" -- SPEC.md: unknown means major
            self.logger.error("EDEN detected a MAJOR fault! Commanding HOLD...")
            self.status = "HOLD"
            cmd = CommandPacket(command="NAV_ADJUST", mode="HOLD", reason="GRACIE_MAJOR")
            self.bus.publish("cmd/nav", cmd.__dict__)
        # Publish on every event, not just a command-triggering one, so the
        # coordinator's EDEN entry stays as current as GRACIE/LUNAE's
        # instead of lagging behind until the next explicit command.
        self.send_status_update()
