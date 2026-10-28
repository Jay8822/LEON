# agents/eden_test.py
# Added 2026-10-28 — Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Checks for EdenAgent's fault-class-aware reaction (Item C), replacing
the old `if health == "FAULT": SAFE_MODE` shortcut. See agents/eden.py's
module docstring for the full mapping (NON_URGENT -> flagged/logged
only, MAJOR -> HOLD via "cmd/nav", BOOM -> SAFE_MODE via "cmd/propulsion",
unknown -> MAJOR).

Publishes synthetic "telemetry/health" payloads directly, same shape
GracieAgent.report_health() actually publishes (readings is a
{channel: {severity, causing_sense, ...}} dict) -- EDEN only cares
about what's on the bus, not who put it there, same convention
agents/ghost_mode_test.py already uses.

Run from the repo root:

    python -m agents.eden_test
"""

from agents.eden import EdenAgent
from agents.escalation_orchestrator import FaultClass
from core.bus import EventBus


def health_payload(health, readings):
    return {"system_health": health, "source": "GRACIE", "timestamp": 0, "readings": readings}


def reading(severity, causing_sense=None):
    return {"value": 0.0, "units": "u", "severity": severity, "jump": False,
            "sensor_health_fault": False, "causing_sense": causing_sense}


def make_eden(fault_class_table=None):
    bus = EventBus()
    commands = []
    bus.subscribe("cmd/nav", commands.append)
    bus.subscribe("cmd/propulsion", commands.append)
    eden = EdenAgent(bus, fault_class_table)
    return eden, commands


def test_non_urgent_flags_and_logs_only_craft_keeps_running():
    table = {"fuel_flow": {"leash_soft": FaultClass.NON_URGENT}}
    eden, commands = make_eden(table)
    eden.on_health_event(health_payload("WARNING", {"fuel_flow": reading("WARNING", "leash_soft")}))
    assert eden.status == "MONITORING", eden.status
    assert commands == [], "a non-urgent fault must never publish a command"
    print("  ok: non-urgent -- flagged and logged, no command, craft keeps running")


def test_major_commands_hold_via_cmd_nav():
    table = {"engine_bay_temp": {"leash_hard": FaultClass.MAJOR}}
    eden, commands = make_eden(table)
    eden.on_health_event(health_payload("FAULT", {"engine_bay_temp": reading("FAULT", "leash_hard")}))
    assert eden.status == "HOLD", eden.status
    assert len(commands) == 1, commands
    assert commands[0]["command"] == "NAV_ADJUST" and commands[0]["mode"] == "HOLD", commands[0]
    print("  ok: major -- HOLD via NAV_ADJUST on cmd/nav, not SAFE_MODE")


def test_boom_commands_safe_mode_via_cmd_propulsion():
    table = {"engine_bay_temp": {"level": FaultClass.BOOM}}
    eden, commands = make_eden(table)
    eden.on_health_event(health_payload("FAULT", {"engine_bay_temp": reading("FAULT", "level")}))
    assert eden.status == "SAFE_MODE", eden.status
    assert len(commands) == 1, commands
    assert commands[0]["command"] == "SAFE_MODE", commands[0]
    print("  ok: boom -- SAFE_MODE via cmd/propulsion, same path as before Item C")


def test_unknown_channel_or_sense_falls_back_to_major():
    eden, commands = make_eden()  # no table at all
    eden.on_health_event(health_payload("FAULT", {"battery_voltage": reading("FAULT", "level")}))
    assert eden.status == "HOLD", eden.status
    assert commands[0]["command"] == "NAV_ADJUST"
    print("  ok: no table entry -- unknown means major, per SPEC.md, not SAFE_MODE")


def test_worst_class_wins_across_multiple_channels_in_one_report():
    table = {
        "fuel_flow": {"leash_soft": FaultClass.NON_URGENT},
        "engine_bay_temp": {"level": FaultClass.BOOM},
    }
    eden, commands = make_eden(table)
    eden.on_health_event(health_payload("FAULT", {
        "fuel_flow": reading("WARNING", "leash_soft"),
        "engine_bay_temp": reading("FAULT", "level"),
    }))
    assert eden.status == "SAFE_MODE", eden.status
    print("  ok: the WORST class among every non-NOMINAL channel wins, not just the first one found")


def test_nominal_never_escalates():
    eden, commands = make_eden()
    eden.on_health_event(health_payload("NOMINAL", {}))
    assert eden.status == "MONITORING", eden.status
    assert commands == []
    print("  ok: NOMINAL never escalates")


def test_default_empty_table_does_not_break_construction():
    """Every existing caller's unqualified EdenAgent(bus) must keep
    working -- the table defaults to {}, not a required argument."""
    bus = EventBus()
    eden = EdenAgent(bus)
    assert eden.fault_class_table == {}
    print("  ok: EdenAgent(bus) with no table still constructs cleanly, defaults to empty")


def main():
    tests = [
        test_non_urgent_flags_and_logs_only_craft_keeps_running,
        test_major_commands_hold_via_cmd_nav,
        test_boom_commands_safe_mode_via_cmd_propulsion,
        test_unknown_channel_or_sense_falls_back_to_major,
        test_worst_class_wins_across_multiple_channels_in_one_report,
        test_nominal_never_escalates,
        test_default_empty_table_does_not_break_construction,
    ]
    for test in tests:
        test()
    print("All EdenAgent fault-class checks passed.")


if __name__ == "__main__":
    main()
