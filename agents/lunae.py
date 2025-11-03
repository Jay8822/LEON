# agents/lunae.py

from core.bus import EventBus
from core.schemas import TelemetryPacket, CommandPacket
import time

class LunaeAgent:
    def __init__(self, bus: EventBus):
        self.bus = bus
        self.current_nav = "CRUISE"

    def process_telemetry(self, telemetry: TelemetryPacket):
        # Example: If in SAFE_MODE, change nav strategy
        if telemetry.system_health == "FAULT":
            print("LUNAE: FAULT detected, switching nav state to HOLD.")
            self.current_nav = "HOLD"
        else:
            self.current_nav = telemetry.nav_state
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
        if cmd == "NAV_ADJUST" and mode:
            print(f"LUNAE: Adjusting navigation to {mode} for reason: {reason}")
            self.current_nav = mode
            self.bus.publish("state/nav", {
                "nav_state": self.current_nav,
                "timestamp": int(time.time()),
                "source": "LUNAE"
            })
