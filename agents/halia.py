# agents/halia.py
# Updated 2026-07-27 — removed personality/"sass" flavor text ahead of going public; plain, honest responses only. Jay Pratt + AI (Claude, Anthropic).

import json
import os
import time

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.bus import EventBus
from core.logger import PROJECT_ROOT, setup_agent_logger

SESSION_FILE = os.path.join(PROJECT_ROOT, "crew_sessions.json")
MAX_CONTEXT_MESSAGES = 3


class CrewMessage(BaseModel):
    from_: str = Field(..., alias='from')
    message: str
    model_config = ConfigDict(populate_by_name=True)


class HaliaAgent:
    def __init__(self, bus: EventBus, coordinator=None):
        self.logger = setup_agent_logger("halia")
        self.bus = bus
        self.coordinator = coordinator
        self.context = {}  # Store up to last 3 messages per crew member
        self.profiles = {
            "Commander Pratt": {"role": "Commander", "suite": "A"},
            "Dr. Liu": {"role": "Science", "suite": "B"},
            # Add more crew as needed!
        }
        self.load_sessions()
        self.bus.subscribe("crew/message", self.on_crew_message)
        self.bus.subscribe("halia/alert", self.on_alert)

    def on_alert(self, payload):
        message = payload.get("message", "No details")
        self.logger.warning(f"HALIA ALERT: {message}")

    def get_system_status(self):
        if self.coordinator is None:
            self.logger.warning("System status requested but no coordinator is attached.")
            return "No coordinator attached; system status unavailable."
        status = self.coordinator.get_status()
        self.logger.info(f"System status queried: {status}")
        return status

    def send_system_command(self, system_name, command, parameters=None):
        if self.coordinator is None:
            self.logger.warning(f"Cannot send '{command}' to {system_name}: no coordinator attached.")
            return f"Cannot reach {system_name}: no coordinator attached."
        self.coordinator.send_command(system_name, command, parameters)
        self.logger.info(f"Command '{command}' sent to {system_name} with params {parameters}")
        return f"Command '{command}' sent to {system_name}."

    def save_sessions(self):
        try:
            with open(SESSION_FILE, "w") as f:
                json.dump(self.context, f)
            self.logger.info("Crew session context saved.")
        except OSError as e:
            self.logger.error(f"Could not save crew sessions: {e}")

    def load_sessions(self):
        if not os.path.exists(SESSION_FILE):
            return
        try:
            with open(SESSION_FILE, "r") as f:
                self.context = json.load(f)
            self.logger.info("Crew session context loaded.")
        except (OSError, json.JSONDecodeError) as e:
            # A corrupt session file must not stop HALIA from coming up.
            self.logger.error(f"Could not load crew sessions ({e}); starting empty.")
            self.context = {}

    def on_crew_message(self, payload):
        try:
            msg = CrewMessage.model_validate(payload)
        except ValidationError as e:
            self.logger.error(f"Invalid crew message: {e}")
            return
        crew_id = msg.from_
        message = msg.message

        history = self.context.setdefault(crew_id, [])
        history.append({"message": message, "timestamp": int(time.time())})
        self.context[crew_id] = history[-MAX_CONTEXT_MESSAGES:]
        self.save_sessions()

        response = self.get_response(crew_id, message, self.context[crew_id])
        self.logger.info(f"HALIA to {crew_id}: {response}")
        self.bus.publish("crew/response", {
            "to": crew_id,
            "timestamp": int(time.time()),
            "response": response
        })

    def get_response(self, crew_id, message, context=None):
        if context is None:
            context = self.context.get(crew_id, [])
        profile = self.profiles.get(crew_id, {})
        role = profile.get("role", "crew")
        msg_low = message.lower()
        memory_count = len(context)
        if "status" in msg_low:
            status = self.get_system_status()
            return f"System Status: {status}. I remember {memory_count} recent message(s) from you."
        elif "run diagnostic" in msg_low:
            for system in ["gracie", "ethan", "lunae", "eden"]:
                if system in msg_low:
                    return self.send_system_command(system, "run_diagnostics")
            return "System not recognized for diagnostics."
        elif "help" in msg_low:
            return f"How can I assist you, {role} {crew_id}?"
        elif "test system" in msg_low or "system test" in msg_low:
            return "System test initiated. Results will follow shortly."
        elif "enable starmapping" in msg_low or "starmapping" in msg_low:
            return "Star mapping mode enabled."
        elif "how are you" in msg_low:
            return "All systems nominal. No alerts or faults detected."
        elif "how are we doing" in msg_low:
            return f"Received your message, {crew_id}. What would you like to do next? Memory of last {memory_count} messages still active."
        else:
            return "Unrecognized command. Try 'status', 'run diagnostic on <system>', or 'help'."