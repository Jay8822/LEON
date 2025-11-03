# agents/ethan_ai.py

from core.bus import EventBus
from core.schemas import CommandPacket
import time

class EthanAgent:
    def __init__(self, bus: EventBus):
        self.bus = bus
        self.current_mode = "NTP"

    def on_command(self, payload):
        cmd = payload.get("command")
        mode = payload.get("mode")
        reason = payload.get("reason")
        if cmd == "SAFE_MODE":
            print(f"ETHAN switching to SAFE_MODE due to: {reason}")
            self.current_mode = "NTP"  # Default safe thrust mode
        elif cmd == "PROPULSION_SET" and mode:
            print(f"ETHAN setting propulsion to {mode}")
            self.current_mode = mode
        # Publish updated state
        self.bus.publish("state/system", {
            "propulsion_mode": self.current_mode,
            "timestamp": int(time.time()),
            "source": "ETHAN_AI"
        })
