# agents/test_halia_gracie.py
# Updated 2026-07-26 — rewritten to use the real shared bus/coordinator, asserts the FAULT alert path. Jay Pratt + AI (Claude, Anthropic).
"""End-to-end check: crew message -> HALIA -> coordinator -> GRACIE -> alert.

Run from the repo root:

    python -m agents.test_halia_gracie
"""

import time

from agents.gracie import GracieAgent
from agents.halia import HaliaAgent
from agents.system_coordinator import SystemCoordinator
from core.bus import EventBus


class TelemetryPacket:
    def __init__(self, temp_c, radiation, timestamp):
        self.temp_c = temp_c
        self.radiation = radiation
        self.timestamp = timestamp


def main():
    bus = EventBus()
    coordinator = SystemCoordinator(bus)
    halia = HaliaAgent(bus, coordinator)
    gracie = GracieAgent(bus)

    alerts = []
    bus.subscribe("halia/alert", alerts.append)
    bus.subscribe("crew/response", lambda p: print(f"HALIA -> {p['to']}: {p['response']}"))

    # HALIA routes this to GRACIE through the coordinator.
    bus.publish("crew/message", {
        "from": "Commander Pratt",
        "message": "run diagnostic on gracie"
    })

    # Telemetry bad enough to trip a FAULT, which must reach HALIA as an alert.
    gracie.process_telemetry(TelemetryPacket(60, 45, int(time.time())))
    assert gracie.health_state == "FAULT", gracie.health_state
    assert alerts, "FAULT did not propagate to halia/alert"
    print(f"Alert received: {alerts[0]}")

    print(f"Coordinator status: {coordinator.get_status()['GRACIE']}")
    print("End-to-end check passed.")


if __name__ == "__main__":
    main()