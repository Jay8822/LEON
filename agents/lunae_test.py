# agents/lunae_test.py
# Added 2026-07-27 — LUNAE had no standalone test; added while fixing its coordinator-visibility gap. Jay Pratt + AI (Claude, Anthropic).
"""Manual check for LUNAE's nav reporting, including the SystemCoordinator
visibility fix: telemetry-driven and command-driven nav updates must both
reach the coordinator, not just the command-driven one.

Run from the repo root:

    python -m agents.lunae_test
"""

from agents.lunae import LunaeAgent
from agents.system_coordinator import SystemCoordinator
from core.bus import EventBus


class TelemetryPacket:
    def __init__(self, system_health, nav_state, timestamp):
        self.system_health = system_health
        self.nav_state = nav_state
        self.timestamp = timestamp


def main():
    bus = EventBus()
    coordinator = SystemCoordinator(bus)
    lunae = LunaeAgent(bus)

    # Before the 2026-07-27 fix, process_telemetry() published to a topic
    # ("state/nav") the coordinator never watched, so this stayed UNKNOWN.
    lunae.process_telemetry(TelemetryPacket("NOMINAL", "CRUISE", 1))
    status = coordinator.get_status()["LUNAE"]
    assert status["nav_state"] == "CRUISE", \
        f"telemetry-driven nav update did not reach the coordinator: {status}"
    print(f"  ok: telemetry-driven nav update reached coordinator: {status}")

    # FAULT telemetry must switch LUNAE to HOLD, and the coordinator must
    # see that too.
    lunae.process_telemetry(TelemetryPacket("FAULT", "CRUISE", 2))
    status = coordinator.get_status()["LUNAE"]
    assert status["nav_state"] == "HOLD", status
    print(f"  ok: FAULT telemetry -> HOLD, visible to coordinator: {status}")

    # Command-driven path must still work identically (this one already did).
    lunae.on_command({"command": "set_nav_state", "parameters": {"nav_state": "IDLE"}})
    status = coordinator.get_status()["LUNAE"]
    assert status["nav_state"] == "IDLE", status
    print(f"  ok: command-driven nav update reached coordinator: {status}")

    print("All LUNAE nav-reporting checks passed.")


if __name__ == "__main__":
    main()
