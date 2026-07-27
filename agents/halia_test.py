# agents/halia_test.py
# Updated 2026-07-27 — malformed-payload check now announces itself and asserts the outcome, rather than a bare ERROR line with no context. Jay Pratt + AI (Claude, Anthropic).
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
    responses = []
    bus.subscribe("crew/response", lambda p: (responses.append(p), print(f"PUBLISH: crew/response {p}")))
    halia = HaliaAgent(bus, DummyCoordinator())

    halia.on_crew_message({"from": "Commander Pratt", "message": "run diagnostic on ethan"})
    halia.on_crew_message({"from": "Dr. Liu", "message": "how are you?"})
    assert len(responses) == 2, "expected exactly 2 responses to the 2 well-formed messages"

    # A payload missing "from" — e.g. a malformed/incomplete publish
    # elsewhere in the system — must be rejected without crashing HALIA
    # or producing a crew response. CrewMessage's Field(...) makes this
    # required, so pydantic raises ValidationError, which on_crew_message
    # catches and logs at ERROR (appropriately: a malformed inbound
    # message is a real problem, just not one that should take HALIA
    # down). This deliberately triggers that path and confirms nothing
    # after it was silently skipped.
    print("Testing rejection of a malformed payload (missing 'from')...")
    halia.on_crew_message({"message": "missing sender"})
    assert len(responses) == 2, "malformed payload should not have produced a crew response"
    print("  ok: malformed payload rejected, no response published, HALIA still running")


if __name__ == "__main__":
    main()