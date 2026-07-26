# agents/halia_test.py
# Updated 2026-07-26 — fixed constructor call to match HaliaAgent(bus, coordinator). Jay Pratt + AI (Claude, Anthropic).
"""Manual check for HALIA's crew-message handling. Run from the repo root:

    python -m agents.halia_test
"""

from agents.halia import HaliaAgent
from core.bus import EventBus


class DummyCoordinator:
    def get_status(self):
        return "All systems normal."

    def send_command(self, system, command, params=None):
        print(f"COMMAND: {system} - {command}")


def main():
    bus = EventBus()
    bus.subscribe("crew/response", lambda p: print(f"PUBLISH: crew/response {p}"))
    halia = HaliaAgent(bus, DummyCoordinator())

    halia.on_crew_message({"from": "Commander Pratt", "message": "run diagnostic on ethan"})
    halia.on_crew_message({"from": "Dr. Liu", "message": "how are you?"})
    # Malformed payloads are logged and dropped, not raised.
    halia.on_crew_message({"message": "missing sender"})


if __name__ == "__main__":
    main()