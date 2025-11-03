# agents/gracie.py

import time
from core.schemas import TelemetryPacket
from core.bus import EventBus

class GracieAgent:
    def __init__(self, bus: EventBus):
        self.bus = bus
        self.health_state = "NOMINAL"

    def process_telemetry(self, telemetry: TelemetryPacket):
        # Basic rules: health checks
        if telemetry.temp_c > 50 or telemetry.radiation > 30:
            self.health_state = "WARNING"
        if telemetry.temp_c > 55 and telemetry.radiation > 40:
            self.health_state = "FAULT"
        else:
            if self.health_state != "FAULT":
                self.health_state = "NOMINAL"
        # Publish health
        self.bus.publish("telemetry/health", {
            "system_health": self.health_state,
            "source": "GRACIE",
            "timestamp": telemetry.timestamp
        })
