# main.py
# Updated 2026-07-26 — single shared bus, fixed startup/console bugs. Jay Pratt + AI (Claude, Anthropic).

import random
import time

from agents.eden import EdenAgent
from agents.escalation_orchestrator import EscalationOrchestrator
from agents.ethan_ai import EthanAgent
from agents.ghost_mode import GhostModeHarness
from agents.gracie import GracieAgent
from agents.halia import HaliaAgent
from agents.lunae import LunaeAgent
from agents.system_coordinator import SystemCoordinator
from core.bus import EventBus
from core.logger import log
from core.schemas import TelemetryPacket

# Ghost mode (task 3 of HANDOVER.md's work queue): placeholder window/
# cycle values, same "no real numbers yet" convention as
# agents/escalation_orchestrator_test.py. Not hardware-derived.
GHOST_MODE_MAJOR_FAULT_WINDOW_SECONDS = 5.0
GHOST_MODE_NON_URGENT_FAULT_WINDOW_SECONDS = 30.0
GHOST_MODE_LIGHT_FLAG_CYCLE_MINUTES = 15.0


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

    # Ghost mode: GRACIE wired into EscalationOrchestrator, watching
    # only. The orchestrator and the harness below do not control
    # anything -- EDEN above is still the only thing that reacts.
    # Subscribed *after* eden.on_health_event on purpose: the harness
    # reads eden.status once EDEN has already reacted to this same
    # event (see agents/ghost_mode.py's module docstring, point 2).
    ghost_orchestrator = EscalationOrchestrator(
        eden_rules={},
        own_rules={},
        major_fault_window_seconds=GHOST_MODE_MAJOR_FAULT_WINDOW_SECONDS,
        non_urgent_fault_window_seconds=GHOST_MODE_NON_URGENT_FAULT_WINDOW_SECONDS,
        light_flag_cycle_minutes=GHOST_MODE_LIGHT_FLAG_CYCLE_MINUTES,
    )
    ghost_mode = GhostModeHarness(bus, eden, ghost_orchestrator)

    bus.subscribe("cmd/propulsion", print_command)
    bus.subscribe("cmd/propulsion", ethan.on_command)
    bus.subscribe("state/system", print_state)
    bus.subscribe("navigation/update", print_nav)
    bus.subscribe("cmd/nav", lunae.on_nav_command)
    bus.subscribe("crew/response", print_crew_response)

    return bus, {
        "coordinator": coordinator,
        "gracie": gracie,
        "ethan": ethan,
        "lunae": lunae,
        "eden": eden,
        "halia": halia,
        "ghost_mode": ghost_mode,
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
        "from": "James Pratt",
        "message": "Halia, how are we doing?"
    })

    run_simulation(bus, agents)
    crew_console(bus)