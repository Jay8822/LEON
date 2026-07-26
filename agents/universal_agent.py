# agents/universal_agent.py
# Updated 2026-07-26 — takes a shared bus instead of importing a global one. Jay Pratt + AI (Claude, Anthropic).

import json
import os
import random
import time

from core.bus import EventBus
from core.logger import PROJECT_ROOT, setup_agent_logger

SKILLS_FILE = os.path.join(PROJECT_ROOT, "universal_agent_skills.json")


class UniversalAgent:
    def __init__(self, bus: EventBus):
        self.logger = setup_agent_logger("universal_agent")
        self.bus = bus
        self.skills = {}
        self.last_json_mtime = 0
        self.load_skills()
        self.bus.subscribe("crew/message", self.on_message)

    def load_skills(self):
        try:
            mtime = os.path.getmtime(SKILLS_FILE)
            if mtime != self.last_json_mtime:
                with open(SKILLS_FILE, "r") as f:
                    self.skills = json.load(f)
                self.last_json_mtime = mtime
                self.logger.info("Skills JSON reloaded.")
        except FileNotFoundError:
            self.logger.error(f"Cannot find skills file: {SKILLS_FILE}")
            self.skills = {}
        except Exception as e:
            self.logger.error(f"Error loading skills: {e}")
            self.skills = {}

    def handle_command(self, subsystem, command, params=None):
        self.load_skills()
        subsystem_tbl = self.skills.get("subsystems", {}).get(subsystem, {})
        cmd_tbl = subsystem_tbl.get("commands", {})
        response = cmd_tbl.get(command)
        if response:
            if params:
                try:
                    return response.format(**params)
                except Exception:
                    return response
            return response
        else:
            return self.skills.get("responses", {}).get("unknown_command", "Unknown command.")

    def get_sample_conversation(self):
        self.load_skills()
        conversations = self.skills.get("conversations", [])
        if conversations:
            convo = random.choice(conversations)
            return f'{convo["from"]} to {convo["to"]}: {convo["message"]}'
        else:
            return "No sample conversations available."

    def on_message(self, payload):
        crew = payload.get("from")
        msg = payload.get("message", "").lower()
        self.logger.info(f"{crew} sent message: '{msg}'")

        # Handle sample chat command
        if "show sample chat" in msg:
            sample = self.get_sample_conversation()
            self.logger.info(f"Sample Chat: {sample}")
            print(f"\n=== Agent to {crew} ===\n{sample}\n")
            self.bus.publish("crew/response", {
                "to": crew,
                "timestamp": int(time.time()),
                "response": sample
            })
            return

        # Try to auto-match subsystem and command
        skill_response = None
        for subsystem, data in self.skills.get("subsystems", {}).items():
            for cmd in data.get("commands", {}):
                if cmd in msg:
                    response = self.handle_command(subsystem, cmd)
                    self.logger.info(f"Responding to {crew}: {response}")
                    print(f"\n=== Agent to {crew} ===\n{response}\n")
                    self.bus.publish("crew/response", {
                        "to": crew,
                        "timestamp": int(time.time()),
                        "response": response
                    })
                    skill_response = True
                    break
            if skill_response:
                break

        if not skill_response:
            unknown = self.skills.get("responses", {}).get("unknown_command", "Unknown command.")
            self.logger.info(f"Unknown command from {crew}. Sending default response.")
            print(f"\n=== Agent to {crew} ===\n{unknown}\n")
            self.bus.publish("crew/response", {
                "to": crew,
                "timestamp": int(time.time()),
                "response": unknown
            })


if __name__ == "__main__":
    bus = EventBus()
    agent = UniversalAgent(bus)
    # Initial test message
    bus.publish("crew/message", {
        "from": "Commander Pratt",
        "message": "show sample chat"
    })

    # Interactive input loop for direct testing
    try:
        while True:
            crew_name = input("Enter crew name (or 'quit'): ")
            if crew_name.lower() in {"quit", "exit"}:
                break
            msg = input("Enter message for agent: ")
            bus.publish("crew/message", {
                "from": crew_name,
                "message": msg
            })
    except (KeyboardInterrupt, EOFError):
        print("Exiting interactive loop.")