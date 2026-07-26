# agents/system_coordinator.py
# Updated 2026-07-26 — watches telemetry/health too, alerts only on the FAULT transition. Jay Pratt + AI (Claude, Anthropic).

import time

from core.bus import EventBus
from core.logger import setup_agent_logger


class SystemCoordinator:
    def __init__(self, bus: EventBus):
        self.logger = setup_agent_logger("system_coordinator")
        self.bus = bus
        self.system_status = {
            "GRACIE": {"health": "UNKNOWN", "last_update": None},
            "ETHAN": {"mode": "IDLE", "last_update": None},
            "LUNAE": {"nav_state": "UNKNOWN", "last_update": None},
            "EDEN": {"status": "UNKNOWN", "last_update": None},
        }
        # Subscribe to system updates. GRACIE reports health on two topics:
        # "health/update" (manual, key "status") and "telemetry/health"
        # (derived from telemetry, key "system_health"). Watch both, or
        # telemetry-driven FAULTs never reach HALIA.
        self.bus.subscribe("health/update", self.on_health_update)
        self.bus.subscribe("telemetry/health", self.on_health_update)
        self.bus.subscribe("navigation/update", self.on_nav_update)
        self.bus.subscribe("propulsion/update", self.on_propulsion_update)
        self.bus.subscribe("eden/status_update", self.on_eden_update)

    def on_health_update(self, payload):
        previous = self.system_status["GRACIE"]["health"]
        health = payload.get("system_health") or payload.get("status") or "UNKNOWN"
        self.system_status["GRACIE"].update({
            "health": health,
            "last_update": payload.get("timestamp", time.time())
        })
        self.logger.info(f"Health update: {payload}")
        # Alert only on the transition into FAULT, not on every repeat packet.
        if health == "FAULT" and previous != "FAULT":
            self.logger.error("GRACIE FAULT detected! Notifying HALIA.")
            self.bus.publish("halia/alert", {"message": "GRACIE FAULT detected!"})

    def on_nav_update(self, payload):
        self.system_status["LUNAE"].update({
            "nav_state": payload.get("nav_state", "UNKNOWN"),
            "last_update": payload.get("timestamp", time.time())
        })
        self.logger.info(f"Navigation update: {payload}")

    def on_propulsion_update(self, payload):
        self.system_status["ETHAN"].update({
            "mode": payload.get("mode", "IDLE"),
            "last_update": payload.get("timestamp", time.time())
        })
        self.logger.info(f"Propulsion update: {payload}")

    def on_eden_update(self, payload):
        self.system_status["EDEN"].update({
            "status": payload.get("status", "UNKNOWN"),
            "last_update": payload.get("timestamp", time.time())
        })
        self.logger.info(f"EDEN update: {payload}")

    def get_status(self):
        self.logger.info(f"Status queried: {self.system_status}")
        return self.system_status

    def send_command(self, system_name, command, parameters=None):
        topic = f"{system_name.lower()}/command"
        payload = {
            "command": command,
            "parameters": parameters or {}
        }
        self.logger.info(f"Sending command: {command} to {system_name} with params {parameters}")
        self.bus.publish(topic, payload)
