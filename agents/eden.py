# agents/eden.py

from core.bus import EventBus
from core.schemas import CommandPacket
import time

class EdenAgent:
    def __init__(self, bus: EventBus):
        self.bus = bus

    def on_health_event(self, payload):
        # If GRACIE reports FAULT, send SAFE_MODE command
        if payload.get("system_health") == "FAULT":
            print("EDEN detected FAULT! Sending SAFE_MODE command...")
            cmd = CommandPacket(
                command="SAFE_MODE",
                mode=None,
                reason="GRACIE_FAULT"
            )
            self.bus.publish("cmd/propulsion", cmd.__dict__)
        # You could expand with more logic for WARNING, etc.
