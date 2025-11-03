# main.py

import time
from core.bus import EventBus
from core.schemas import TelemetryPacket
from agents.gracie import GracieAgent
from agents.eden import EdenAgent
from agents.ethan_ai import EthanAgent
from agents.lunae import LunaeAgent
from agents.halia import HaliaAgent
from core.logger import log


def simulate_environment():
    import random
    return TelemetryPacket(
        timestamp=int(time.time()),
        temp_c=random.uniform(30, 60),
        radiation=random.uniform(5, 50),
        thrust_demand=random.uniform(0, 1),
        nav_state="CRUISE",
        system_health="NOMINAL",
        source="ENV"
    )

def print_health(payload):
    print(f"Health update from {payload['source']}: {payload['system_health']} at {payload['timestamp']}")
    log(f"Health update from {payload['source']}: {payload['system_health']} at {payload['timestamp']}")

def print_command(payload):
    print(f"Command issued: {payload}")
    log(f"Command issued: {payload}")

def print_state(payload):
    print(f"System state update: {payload}")
    log(f"System state update: {payload}")

def print_crew_response(payload):
    print(f"Crew response: {payload}")
    log(f"Crew response: {payload}")

if __name__ == "__main__":
    bus = EventBus()
    gracie = GracieAgent(bus)
    eden = EdenAgent(bus)
    ethan = EthanAgent(bus)
    lunae = LunaeAgent(bus)
    halia = HaliaAgent(bus)

    bus.subscribe("telemetry/health", print_health)
    bus.subscribe("telemetry/health", eden.on_health_event)
    bus.subscribe("cmd/propulsion", print_command)
    bus.subscribe("cmd/propulsion", ethan.on_command)
    bus.subscribe("state/system", lambda p: print(f"System state update: {p}"))
    bus.subscribe("state/nav", lambda p: print(f"Navigation state update: {p}"))
    bus.subscribe("cmd/nav", lunae.on_nav_command)
    bus.subscribe("crew/response", print_crew_response)
    # Example: Send a message from "Commander Pratt" after simulation ends
    bus.publish("crew/message", {
        "from": "Commander Pratt",
        "message": "Halia, how are we doing?"
    })
    for _ in range(10):
        telemetry = simulate_environment()
        gracie.process_telemetry(telemetry)
        lunae.process_telemetry(telemetry)
        
        time.sleep(1)
