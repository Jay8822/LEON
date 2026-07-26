# agents/ethan_ai.py
# Updated 2026-07-26 — fixed imports, added run_diagnostics handling. Jay Pratt + AI (Claude, Anthropic).

import time

from core.bus import EventBus
from core.logger import setup_agent_logger
from core.schemas import CommandPacket


class EthanAgent:
    def __init__(self, bus: EventBus):
        self.logger = setup_agent_logger("ethan_ai")
        self.bus = bus
        self.current_mode = "NTP"
        self.bus.subscribe("ethan/command", self.on_command)
        # Initialize other states as needed

    def send_status_update(self, mode):
        payload = {
            "mode": mode,
            "timestamp": int(time.time())
        }
        self.logger.info(f"Status update: {payload}")
        self.bus.publish("propulsion/update", payload)

    def on_command(self, payload):
        # Combine your two versions of on_command!
        command = payload.get("command")
        parameters = payload.get("parameters", {})
        mode = payload.get("mode")
        reason = payload.get("reason")

        self.logger.info(f"Received command: {command} with payload {payload}")

        # Safemode logic
        if command == "SAFE_MODE" or command == "system_test":
            self.logger.warning(f"Switching to SAFE_MODE due to: {reason}") if reason else self.logger.info("Running system test")
            self.current_mode = "NTP"
            self.send_status_update("TESTING" if command == "system_test" else "SAFE_MODE")
            # Simulate completion
            self.send_status_update("NOMINAL")
        elif command == "run_diagnostics":
            self.logger.info("Running diagnostics")
            self.send_status_update("TESTING")
            # Simulate diagnostic done; propulsion mode is unaffected.
            self.send_status_update(self.current_mode)
        elif command == "PROPULSION_SET" and mode:
            self.logger.info(f"Setting propulsion to {mode}")
            self.current_mode = mode
            self.send_status_update(mode)
        elif command == "switch_mode":
            new_mode = parameters.get("mode", "IDLE")
            self.logger.info(f"Switching mode to {new_mode}")
            self.current_mode = new_mode
            self.send_status_update(new_mode)
        
        # Always publish updated state
        self.bus.publish("state/system", {
            "propulsion_mode": self.current_mode,
            "timestamp": int(time.time()),
            "source": "ETHAN_AI"
        })

