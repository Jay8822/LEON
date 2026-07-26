# agents/lunae.py
# Updated 2026-07-26 — fixed broken imports/logger setup. Jay Pratt + AI (Claude, Anthropic).

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

    def send_nav_update(self):
        payload = {
            "nav_state": self.nav_state,
            "timestamp": int(time.time())
        }
        self.logger.info(f"Navigation state update: {payload}")
        self.bus.publish("navigation/update", payload)

    def on_command(self, payload):
        command = payload.get("command")
        self.logger.info(f"Received command: {command} with payload {payload}")
        if command == "set_nav_state":
            new_state = payload.get("parameters", {}).get("nav_state", "IDLE")
            self.nav_state = new_state
            self.logger.info(f"Navigation set to: {new_state}")
            self.send_nav_update()
        elif command == "run_diagnostics":
            # Example diagnostic routine
            self.logger.info("Running diagnostics")
            # After diagnostics, send current status
            self.send_nav_update()

    def process_telemetry(self, telemetry: TelemetryPacket):
        prior_nav = self.current_nav
        if telemetry.system_health == "FAULT":
            self.logger.error("FAULT detected, switching nav state to HOLD.")
            self.current_nav = "HOLD"
        else:
            self.current_nav = telemetry.nav_state
        self.logger.info(f"Processed telemetry. Nav: {prior_nav} => {self.current_nav}")
        # Publish navigation state update
        self.bus.publish("state/nav", {
            "nav_state": self.current_nav,
            "timestamp": int(time.time()),
            "source": "LUNAE"
        })

    def on_nav_command(self, payload):
        cmd = payload.get("command")
        mode = payload.get("mode")
        reason = payload.get("reason")
        self.logger.info(f"Received nav command: {cmd} mode={mode} reason={reason}")
        if cmd == "NAV_ADJUST" and mode:
            self.logger.info(f"Adjusting navigation to {mode} for reason: {reason}")
            self.current_nav = mode
            self.bus.publish("state/nav", {
                "nav_state": self.current_nav,
                "timestamp": int(time.time()),
                "source": "LUNAE"
            })
