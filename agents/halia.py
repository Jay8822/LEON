# agents/halia.py

from core.bus import EventBus
import random
import time

class HaliaAgent:
    def __init__(self, bus: EventBus):
        self.bus = bus
        self.quotes = [
            "Remember, every great journey starts with a single step.",
            "You’ve got this, and I’m here for you.",
            "Let’s keep the ship steady—and spirits up!",
            "No matter how far from Earth—you are never alone.",
        ]
        self.bus.subscribe("crew/message", self.on_crew_message)

    def on_crew_message(self, payload):
        crew_name = payload.get("from", "crew")
        message = payload.get("message", "")
        # Respond with empathy, encouragement, or a wise crack
        response = random.choice(self.quotes)
        print(f"HALIA to {crew_name}: {response}")
        self.bus.publish("crew/response", {
            "to": crew_name,
            "timestamp": int(time.time()),
            "response": response
        })
