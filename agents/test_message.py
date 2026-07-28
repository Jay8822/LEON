# agents/test_message.py
# Updated 2026-07-26 — wired into a real bus/coordinator/HALIA instead of the dead standalone bus. Jay Pratt + AI (Claude, Anthropic).
"""Publish a single crew message into a fully wired system.

Run from the repo root:

    python -m agents.test_message
"""

from agents.halia import HaliaAgent
from agents.system_coordinator import SystemCoordinator
from core.bus import EventBus


def main():
    bus = EventBus()
    coordinator = SystemCoordinator(bus)
    HaliaAgent(bus, coordinator)
    bus.subscribe("crew/response", lambda p: print(f"HALIA -> {p['to']}: {p['response']}"))

    bus.publish("crew/message", {
        "from": "James Pratt",
        "message": "run diagnostic on gracie"
    })


if __name__ == "__main__":
    main()