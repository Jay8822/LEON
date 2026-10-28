# main.py
# Updated 2026-07-26 — single shared bus, fixed startup/console bugs. Jay Pratt + AI (Claude, Anthropic).

import random
import time

from agents.chester import ChesterAgent
from agents.eden import EdenAgent
from agents.escalation_orchestrator import EscalationOrchestrator
from agents.ethan_ai import EthanAgent
from agents.ghost_mode import GhostModeHarness
from agents.gracie import GracieAgent
from agents.gracie_rulebook import ChannelRule
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

# CHESTER: placeholder settings, same "no real numbers yet" convention.
# SPEC.md: "10 minutes is the intended starting value" for the ghost-
# memory refresh -- not claimed as real here either, just a shorter
# value so the demo can actually show a refresh happening.
CHESTER_REFRESH_PERIOD_SECONDS = 60.0
CHESTER_MAX_LAYERS = 5


def _chester_nothing_is_irrelevant(entry):
    """Placeholder end-of-mission tidy filter: nothing is dropped from
    ghost memory yet. A real rule-book-driven filter is future work."""
    return False

# GRACIE's rule book (any-sensor upgrade): placeholder demo values,
# same "no real numbers yet" convention as everything else above --
# not hardware-calibrated, chosen only to roughly match
# simulate_environment()'s random ranges below so the demo still
# occasionally crosses a threshold, same as the old scaffolding did.
GRACIE_RULE_BOOK = {
    "temp_c": ChannelRule(
        name="temp_c", units="C",
        level_high=55.0, level_low=-50.0,
        jump_limit=10.0,
        leash_window_seconds=5.0, leash_slope_limit=2.0,
        leash_soft_duration_seconds=10.0, leash_hard_duration_seconds=20.0,
        stuck_window_seconds=5.0, min_normal_noise=0.0,  # Stillness not exercised here
        level_fault_class=None, jump_fault_class=None, leash_soft_fault_class=None,
        leash_hard_fault_class=None, stillness_fault_class=None,  # Item C: not stated this round
    ),
    "radiation": ChannelRule(
        name="radiation", units="rad",
        level_high=40.0, level_low=0.0,
        jump_limit=10.0,
        leash_window_seconds=5.0, leash_slope_limit=2.0,
        leash_soft_duration_seconds=10.0, leash_hard_duration_seconds=20.0,
        stuck_window_seconds=5.0, min_normal_noise=0.0,  # Stillness not exercised here
        level_fault_class=None, jump_fault_class=None, leash_soft_fault_class=None,
        leash_hard_fault_class=None, stillness_fault_class=None,  # Item C: not stated this round
    ),
}


def build_system():
    """Create the one bus every agent shares, and wire the agents to it."""
    bus = EventBus()

    coordinator = SystemCoordinator(bus)
    gracie = GracieAgent(bus, GRACIE_RULE_BOOK)
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

    # CHESTER: watches "chester/watch" (GRACIE already announces on it)
    # and the orchestrator's ignored-agent ping. No authority -- purely
    # observing, same spirit as ghost mode above.
    chester = ChesterAgent(
        bus, ghost_orchestrator,
        CHESTER_REFRESH_PERIOD_SECONDS, CHESTER_MAX_LAYERS,
        _chester_nothing_is_irrelevant,
    )

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
        "chester": chester,
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
        # GRACIE now takes her own, any-sensor input shape rather than
        # the shared TelemetryPacket -- see agents/gracie.py's module
        # docstring, point 2. LUNAE's own call is unchanged.
        agents["gracie"].process_readings(
            {"temp_c": telemetry.temp_c, "radiation": telemetry.radiation},
            telemetry.timestamp,
        )
        agents["lunae"].process_telemetry(telemetry)
        agents["chester"].tick(telemetry.timestamp)
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