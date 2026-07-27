# agents/gracie.py
# Updated 2026-07-26 — fixed WARNING state, added FAULT latch. Jay Pratt + AI (Claude, Anthropic).

import time

from core.bus import EventBus
from core.logger import setup_agent_logger


class GracieAgent:
    def __init__(self, bus: EventBus):
        self.logger = setup_agent_logger("gracie")
        self.bus = bus
        self.health_state = "NOMINAL"
        self.bus.subscribe("gracie/command", self.on_command)

    def on_command(self, payload):
        command = payload.get("command")
        self.logger.info(f"Received command: {command} with payload {payload}")
        if command == "run_diagnostics":
            self.report_health()
        elif command == "clear_fault":
            self.health_state = "NOMINAL"
            self.logger.info("FAULT cleared, health reset to NOMINAL.")
            self.report_health()

    def process_telemetry(self, telemetry):
        # Basic rules: health checks. FAULT latches until an explicit
        # clear_fault command, so a single good reading cannot mask it.
        prior_state = self.health_state
        if telemetry.temp_c > 55 and telemetry.radiation > 40:
            self.health_state = "FAULT"
        elif self.health_state != "FAULT":
            if telemetry.temp_c > 50 or telemetry.radiation > 30:
                self.health_state = "WARNING"
            else:
                self.health_state = "NOMINAL"
        self.logger.info(f"Processed telemetry (temp: {telemetry.temp_c}, rad: {telemetry.radiation}) "
                         f"State: {prior_state} => {self.health_state}")
        self.report_health(telemetry.timestamp)

    def report_health(self, timestamp=None):
        # Single publish path for every trigger (telemetry, run_diagnostics,
        # clear_fault) on the single topic every subscriber — SystemCoordinator
        # *and* EDEN — listens on. Previously run_diagnostics/clear_fault
        # published to a separate "health/update" topic that only the
        # coordinator watched, so a diagnostic-triggered FAULT report never
        # reached EDEN the way a telemetry-triggered one did.
        if timestamp is None:
            timestamp = int(time.time())
        self.logger.info(f"Reporting health: {self.health_state}")
        self.bus.publish("telemetry/health", {
            "system_health": self.health_state,
            "source": "GRACIE",
            "timestamp": timestamp
        })