# agents/gracie_test.py
# Updated 2026-07-26 — rewritten as a real check with assertions. Jay Pratt + AI (Claude, Anthropic).
"""Manual check for GRACIE's health-state rules. Run from the repo root:

    python -m agents.gracie_test
"""

from agents.gracie import GracieAgent
from core.bus import EventBus


class TelemetryPacket:
    def __init__(self, temp_c, radiation, timestamp):
        self.temp_c = temp_c
        self.radiation = radiation
        self.timestamp = timestamp


def main():
    bus = EventBus()
    bus.subscribe("telemetry/health", lambda p: print(f"PUBLISH: telemetry/health {p}"))
    gracie = GracieAgent(bus)

    # NOMINAL -> WARNING -> FAULT (and FAULT latches).
    for temp, rad, expected in [
        (30, 10, "NOMINAL"),
        (52, 10, "WARNING"),   # would have been wrongly reported NOMINAL before
        (56, 41, "FAULT"),
        (30, 10, "FAULT"),     # FAULT latches until cleared
    ]:
        gracie.process_telemetry(TelemetryPacket(temp, rad, 1234567890))
        assert gracie.health_state == expected, \
            f"temp={temp} rad={rad}: expected {expected}, got {gracie.health_state}"
        print(f"  ok: temp={temp} rad={rad} -> {expected}")

    gracie.on_command({"command": "clear_fault"})
    assert gracie.health_state == "NOMINAL"
    print("  ok: clear_fault -> NOMINAL")
    print("All GRACIE health-state checks passed.")


if __name__ == "__main__":
    main()