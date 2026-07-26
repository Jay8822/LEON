# agents/eden.py
# Updated 2026-07-26 — status heartbeat on every health event, not just on command. Jay Pratt + AI (Claude, Anthropic).

import time

from core.bus import EventBus
from core.logger import setup_agent_logger
from core.schemas import CommandPacket


class EdenAgent:
    def __init__(self, bus: EventBus):
        self.logger = setup_agent_logger("eden")
        self.bus = bus
        self.bus.subscribe("eden/command", self.on_command)
        self.status = "IDLE"

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

    def on_health_event(self, payload):
        # If GRACIE reports FAULT, send SAFE_MODE command
        health = payload.get("system_health")
        self.logger.info(f"Health event received: {health}")
        if health == "FAULT":
            self.logger.error("EDEN detected FAULT! Sending SAFE_MODE command...")
            self.status = "SAFE_MODE"
            cmd = CommandPacket(
                command="SAFE_MODE",
                mode=None,
                reason="GRACIE_FAULT"
            )
            self.bus.publish("cmd/propulsion", cmd.__dict__)
        # You could expand with more logic for WARNING, etc.
        else:
            self.status = "MONITORING"
        # Publish on every event, not just FAULT, so the coordinator's EDEN
        # entry stays as current as GRACIE/LUNAE's instead of lagging behind
        # until the next explicit command.
        self.send_status_update()
