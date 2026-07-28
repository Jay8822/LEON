# agents/orchestrator.py
# Updated 2026-07-26 — fixed step-ordering bug, uses shared bus. Jay Pratt + AI (Claude, Anthropic).

from core.bus import EventBus
from core.logger import setup_agent_logger


class Orchestrator:
    def __init__(self, bus: EventBus):
        self.logger = setup_agent_logger("orchestrator")
        self.bus = bus
        self.step = 0
        self.bus.subscribe("crew/response", self.on_response)

    def start_diagnostics(self):
        self.logger.info("Starting system diagnostics...")
        self.step = 1
        self.bus.publish("crew/message", {"from": "James Pratt", "message": "run diagnostic on gracie"})

    def on_response(self, payload):
        response = payload.get("response", "")
        if self.step == 1:
            self.logger.info(f"Step 1: Received response: {response}")
            self.logger.info("Proceeding to next step after Gracie diagnostic.")
            # Advance before publishing: publish is synchronous, so the
            # response to this message arrives before publish() returns.
            self.step = 2
            self.bus.publish("crew/message", {"from": "James Pratt", "message": "run diagnostic on ethan"})
        elif self.step == 2:
            self.logger.info(f"Step 2: Received response: {response}")
            self.logger.info("Diagnostics complete.")
            self.step = 3


# To test:
if __name__ == "__main__":
    from agents.halia import HaliaAgent
    from agents.system_coordinator import SystemCoordinator

    bus = EventBus()
    coordinator = SystemCoordinator(bus)
    HaliaAgent(bus, coordinator)
    Orchestrator(bus).start_diagnostics()
