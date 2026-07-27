# agents/test_halia_gracie.py
# Updated 2026-07-27 — also asserts the run_diagnostics path reaches EDEN, same as telemetry. Jay Pratt + AI (Claude, Anthropic).
"""End-to-end check: crew message -> HALIA -> coordinator -> GRACIE -> alert,
and that EDEN reacts identically whether GRACIE's FAULT report was triggered
by telemetry or by a "run diagnostic" command.

Run from the repo root:

    python -m agents.test_halia_gracie
"""

import time

from agents.eden import EdenAgent
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
    eden = EdenAgent(bus)
    bus.subscribe("telemetry/health", eden.on_health_event)

    alerts = []
    commands = []
    bus.subscribe("halia/alert", alerts.append)
    bus.subscribe("cmd/propulsion", commands.append)
    bus.subscribe("crew/response", lambda p: print(f"HALIA -> {p['to']}: {p['response']}"))

    # Telemetry bad enough to trip a FAULT: must alert HALIA *and* make
    # EDEN issue SAFE_MODE.
    gracie.process_telemetry(TelemetryPacket(60, 45, int(time.time())))
    assert gracie.health_state == "FAULT", gracie.health_state
    assert alerts, "FAULT did not propagate to halia/alert"
    assert commands and commands[-1]["command"] == "SAFE_MODE", \
        "telemetry-triggered FAULT did not make EDEN issue SAFE_MODE"
    print(f"Alert received: {alerts[0]}")
    print(f"EDEN command (telemetry path): {commands[-1]}")

    # Now trigger the SAME still-latched FAULT via the command path
    # (what "run diagnostic on gracie" does) instead of new telemetry.
    # Before the 2026-07-27 fix, this reported to a topic only the
    # coordinator watched, so EDEN never saw it and never re-issued
    # SAFE_MODE here.
    commands.clear()
    bus.publish("crew/message", {
        "from": "Commander Pratt",
        "message": "run diagnostic on gracie"
    })
    assert commands and commands[-1]["command"] == "SAFE_MODE", \
        "run_diagnostics path did not reach EDEN the way telemetry did"
    print(f"EDEN command (run_diagnostics path): {commands[-1]}")

    print(f"Coordinator status: {coordinator.get_status()['GRACIE']}")
    print("End-to-end check passed.")


if __name__ == "__main__":
    main()