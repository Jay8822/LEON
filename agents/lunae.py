# agents/lunae.py
# Updated 2026-07-27 — unified nav reporting onto one topic so the coordinator sees telemetry-driven updates too. Jay Pratt + AI (Claude, Anthropic).

import time

from core.bus import EventBus
from core.logger import setup_agent_logger
from core.schemas import CommandPacket, TelemetryPacket


class LunaeAgent:
    def __init__(self, bus: EventBus):
        self.logger = setup_agent_logger("lunae")
        self.bus = bus
        self.current_nav = "CRUISE"
        self.bus.subscribe("lunae/command", self.on_command)
        # Initialize navigation state
        self.nav_state = "IDLE"

    def report_nav(self, nav_state=None, timestamp=None):
        # Single publish path for every trigger (telemetry, set_nav_state,
        # run_diagnostics, NAV_ADJUST) on the one topic SystemCoordinator
        # actually watches. Previously process_telemetry() and
        # on_nav_command() published to "state/nav" (which only main.py's
        # print handler watched), so the coordinator's LUNAE entry stayed
        # UNKNOWN under normal telemetry-driven operation and only updated
        # via an explicit lunae/command.
        if nav_state is not None:
            self.current_nav = nav_state
        if timestamp is None:
            timestamp = int(time.time())
        payload = {
            "nav_state": self.current_nav,
            "timestamp": timestamp,
            "source": "LUNAE"
        }
        self.logger.info(f"Navigation state update: {payload}")
        self.bus.publish("navigation/update", payload)

    def on_command(self, payload):
        command = payload.get("command")
        self.logger.info(f"Received command: {command} with payload {payload}")
        if command == "set_nav_state":
            new_state = payload.get("parameters", {}).get("nav_state", "IDLE")
            self.logger.info(f"Navigation set to: {new_state}")
            self.report_nav(new_state)
        elif command == "run_diagnostics":
            self.logger.info("Running diagnostics")
            self.report_nav()

    def process_telemetry(self, telemetry: TelemetryPacket):
        prior_nav = self.current_nav
        if telemetry.system_health == "FAULT":
            self.logger.error("FAULT detected, switching nav state to HOLD.")
            new_nav = "HOLD"
        else:
            new_nav = telemetry.nav_state
        self.logger.info(f"Processed telemetry. Nav: {prior_nav} => {new_nav}")
        self.report_nav(new_nav, telemetry.timestamp)

    def on_nav_command(self, payload):
        cmd = payload.get("command")
        mode = payload.get("mode")
        reason = payload.get("reason")
        self.logger.info(f"Received nav command: {cmd} mode={mode} reason={reason}")
        if cmd == "NAV_ADJUST" and mode:
            self.logger.info(f"Adjusting navigation to {mode} for reason: {reason}")
            self.report_nav(mode)
