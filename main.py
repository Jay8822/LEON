# main.py
# Updated 2026-07-26 — single shared bus, fixed startup/console bugs. Jay Pratt + AI (Claude, Anthropic).

import random
import time

from agents.eden import EdenAgent
from agents.ethan_ai import EthanAgent
from agents.gracie import GracieAgent
from agents.halia import HaliaAgent
from agents.lunae import LunaeAgent
from agents.system_coordinator import SystemCoordinator
from core.bus import EventBus
from core.logger import log
from core.schemas import TelemetryPacket


def build_system():
    """Create the one bus every agent shares, and wire the agents to it."""
    bus = EventBus()

    coordinator = SystemCoordinator(bus)
    gracie = GracieAgent(bus)
    ethan = EthanAgent(bus)
    lunae = LunaeAgent(bus)
    eden = EdenAgent(bus)
    halia = HaliaAgent(bus, coordinator)

    bus.subscribe("telemetry/health", print_health)
    bus.subscribe("telemetry/health", eden.on_health_event)
    bus.subscribe("cmd/propulsion", print_command)
    bus.subscribe("cmd/propulsion", ethan.on_command)
    bus.subscribe("state/system", print_state)
    bus.subscribe("state/nav", print_nav)
    bus.subscribe("cmd/nav", lunae.on_nav_command)
    bus.subscribe("crew/response", print_crew_response)

    return bus, {
        "coordinator": coordinator,
        "gracie": gracie,
        "ethan": ethan,
        "lunae": lunae,
        "eden": eden,
        "halia": halia,
    }


def simulate_environment():
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
    message = (f"Health update from {payload['source']}: "
               f"{payload['system_health']} at {payload['timestamp']}")
    print(message)
    log(message)


def print_command(payload):
    print(f"Command issued: {payload}")
    log(f"Command issued: {payload}")


def print_state(payload):
    print(f"System state update: {payload}")
    log(f"System state update: {payload}")


def print_nav(payload):
    print(f"Navigation state update: {payload}")
    log(f"Navigation state update: {payload}")


def print_crew_response(payload):
    print(f"Crew response: {payload}")
    log(f"Crew response: {payload}")


def run_simulation(bus, agents, cycles=10, delay=1.0):
    for _ in range(cycles):
        telemetry = simulate_environment()
        agents["gracie"].process_telemetry(telemetry)
        agents["lunae"].process_telemetry(telemetry)
        time.sleep(delay)


def crew_console(bus):
    """Interactive prompt. HALIA replies synchronously via print_crew_response."""
    while True:
        try:
            # strip() also drops a BOM when stdin is piped in on Windows.
            crew_id = input("Crew name (or 'quit' to exit): ").strip().lstrip("﻿")
            if crew_id.lower() in {"quit", "exit"}:
                break
            if not crew_id:
                continue
            message = input(f"{crew_id} to HALIA > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not message:
            continue
        bus.publish("crew/message", {
            "from": crew_id,
            "message": message
        })


if __name__ == "__main__":
    bus, agents = build_system()

    bus.publish("crew/message", {
        "from": "Commander Pratt",
        "message": "Halia, how are we doing?"
    })

    run_simulation(bus, agents)
    crew_console(bus)