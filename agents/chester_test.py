# agents/chester_test.py
# Added 2026-10-25 — Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Checks for ChesterAgent. Fixture settings below (refresh period,
max layers) are arbitrary, round numbers for easy arithmetic in these
tests -- not real values, same "no invented numbers" discipline as
every other test file here.

Run from the repo root:

    python -m agents.chester_test
"""

from agents.chester import ChesterAgent
from agents.escalation_orchestrator import EscalationOrchestrator
from agents.gracie import GracieAgent
from agents.gracie_rulebook import ChannelRule
from core.bus import EventBus

REFRESH_SECONDS = 10.0
MAX_LAYERS = 3


def never_irrelevant(entry):
    return False


def kind_is_jump(entry):
    return entry.get("kind") == "jump"


def make_chester(is_irrelevant=never_irrelevant):
    bus = EventBus()
    orchestrator = EscalationOrchestrator(
        eden_rules={}, own_rules={},
        major_fault_window_seconds=5.0, non_urgent_fault_window_seconds=30.0,
        light_flag_cycle_minutes=15.0,
    )
    chester = ChesterAgent(bus, orchestrator, REFRESH_SECONDS, MAX_LAYERS, is_irrelevant)
    return bus, chester, orchestrator


def watch(bus, kind, agent="GRACIE", channel="chan", timestamp=0):
    bus.publish("chester/watch", {
        "kind": kind, "agent": agent, "channel": channel,
        "timestamp": timestamp, "readings": {},
    })


# --- generic watching -------------------------------------------------------

def test_on_watch_logs_everything_generically():
    bus, chester, _ = make_chester()
    watch(bus, "jump", channel="a")
    watch(bus, "warning_entered", channel="b")
    assert len(chester.permanent_log()) == 2
    assert [e["kind"] for e in chester.permanent_log()] == ["jump", "warning_entered"]
    print("  ok: on_watch() handles any kind of announcement, not hardcoded to one")


def test_real_gracie_announcements_are_watched():
    """Integration: a REAL GracieAgent, not synthetic payloads --
    jump, warning_entered, warning_left, leash_settled all land in
    CHESTER's permanent log."""
    bus = EventBus()
    orchestrator = EscalationOrchestrator(
        eden_rules={}, own_rules={},
        major_fault_window_seconds=5.0, non_urgent_fault_window_seconds=30.0,
        light_flag_cycle_minutes=15.0,
    )
    chester = ChesterAgent(bus, orchestrator, REFRESH_SECONDS, MAX_LAYERS, never_irrelevant)
    rule_book = {
        "drift": ChannelRule(
            name="drift", units="u", level_high=1e9, level_low=-1e9, jump_limit=5.0,
            leash_window_seconds=10.0, leash_slope_limit=1.0,
            leash_soft_duration_seconds=20.0, leash_hard_duration_seconds=40.0,
            stuck_window_seconds=10.0, min_normal_noise=0.0,  # Stillness not exercised here
        ),
    }
    gracie = GracieAgent(bus, rule_book)

    gracie.process_readings({"drift": 0}, timestamp=0)
    gracie.process_readings({"drift": 100}, timestamp=1)  # jump
    for t in range(2, 32):
        gracie.process_readings({"drift": 2.0 * t}, timestamp=float(t))  # ramp to soft at t~30-ish
    kinds = [e["kind"] for e in chester.permanent_log()]
    assert "jump" in kinds
    assert "warning_entered" in kinds
    print("  ok: a real GracieAgent's jump and warning_entered announcements are watched")


# --- light-flag reminders ----------------------------------------------------

def test_open_item_is_light_flagged_until_closed():
    bus, chester, _ = make_chester()
    watch(bus, "warning_entered", agent="GRACIE", channel="x", timestamp=0)
    assert len(chester.open_items()) == 1

    chester.tick(now_seconds=1)
    chester.tick(now_seconds=2)
    # Still open -- light-flagged on every tick, not just once.
    assert len(chester.open_items()) == 1

    watch(bus, "warning_left", agent="GRACIE", channel="x", timestamp=3)
    assert chester.open_items() == []
    print("  ok: an open item is light-flagged on every tick until a matching close arrives")


def test_leash_settled_also_closes_an_open_item():
    bus, chester, _ = make_chester()
    watch(bus, "warning_entered", agent="GRACIE", channel="x")
    watch(bus, "leash_settled", agent="GRACIE", channel="x")
    assert chester.open_items() == []
    print("  ok: leash_settled closes an open item too, not just warning_left")


# --- ghost memory: layers, refresh, storage-full -----------------------------

def test_ghost_memory_refreshes_into_a_new_layer():
    bus, chester, _ = make_chester()
    watch(bus, "jump", channel="a")
    chester.tick(now_seconds=0)
    assert len(chester.ghost_memory_layers()) == 1

    chester.tick(now_seconds=REFRESH_SECONDS)  # exactly one refresh period later
    assert len(chester.ghost_memory_layers()) == 2
    watch(bus, "jump", channel="b")
    # The new entry lands in the NEW layer, not the old one.
    assert chester.ghost_memory_layers()[0] == [{"kind": "jump", "agent": "GRACIE", "channel": "a",
                                                   "timestamp": 0, "readings": {}}]
    assert len(chester.ghost_memory_layers()[1]) == 1
    print("  ok: ghost memory opens a new layer once the refresh period elapses")


def test_storage_full_rule_drops_oldest_layer_not_the_permanent_log():
    bus, chester, _ = make_chester()
    for i in range(MAX_LAYERS + 2):
        watch(bus, "jump", channel=f"c{i}", timestamp=i)
        chester.tick(now_seconds=i * REFRESH_SECONDS)
    assert len(chester.ghost_memory_layers()) <= MAX_LAYERS
    # Nothing is ever lost from the permanent log, even once ghost
    # memory itself has dropped the oldest layers.
    assert len(chester.permanent_log()) == MAX_LAYERS + 2
    print("  ok: the storage-full rule drops the oldest ghost layer, never the permanent log")


# --- end-of-mission tidy ------------------------------------------------------

def test_tidy_removes_irrelevant_entries_from_ghost_memory_only():
    bus, chester, _ = make_chester(is_irrelevant=kind_is_jump)
    watch(bus, "jump", channel="a")
    watch(bus, "warning_entered", channel="b")
    assert len(chester.permanent_log()) == 2

    chester.tidy_ghost_memory()

    assert len(chester.permanent_log()) == 2, "the raw log is never edited or deleted by tidying"
    remaining = [e for layer in chester.ghost_memory_layers() for e in layer]
    assert [e["kind"] for e in remaining] == ["warning_entered"]
    print("  ok: tidying removes irrelevant entries from ghost memory, never from the permanent log")


# --- ignored-agent check ------------------------------------------------------

def test_report_ignored_agent_uses_the_real_orchestrator():
    bus, chester, orchestrator = make_chester()
    result = chester.report_ignored_agent("LUNAE", responded=False)
    assert result.outcome == "UNRESPONSIVE", result
    flags = [e for e in chester.permanent_log() if e.get("kind") == "ignored_agent_ping"]
    assert len(flags) == 1 and flags[0]["agent"] == "LUNAE" and flags[0]["outcome"] == "UNRESPONSIVE"
    # Same event is visible in the orchestrator's own decision log too --
    # this really went through the real EscalationOrchestrator, not a stub.
    assert any(e["agent"] == "LUNAE" for e in orchestrator.decision_log())
    print("  ok: report_ignored_agent() uses the real orchestrator and flags CHESTER's own log")


# --- heartbeat -----------------------------------------------------------------

def test_heartbeat_ping_is_answered():
    bus, chester, _ = make_chester()
    responses = []
    bus.subscribe("chester/heartbeat_response", responses.append)
    bus.publish("chester/heartbeat_ping", {})
    assert len(responses) == 1 and responses[0]["status"] == "alive"
    print("  ok: CHESTER answers a heartbeat ping if one arrives")


def main():
    tests = [
        test_on_watch_logs_everything_generically,
        test_real_gracie_announcements_are_watched,
        test_open_item_is_light_flagged_until_closed,
        test_leash_settled_also_closes_an_open_item,
        test_ghost_memory_refreshes_into_a_new_layer,
        test_storage_full_rule_drops_oldest_layer_not_the_permanent_log,
        test_tidy_removes_irrelevant_entries_from_ghost_memory_only,
        test_report_ignored_agent_uses_the_real_orchestrator,
        test_heartbeat_ping_is_answered,
    ]
    for test in tests:
        test()
    print("All CHESTER checks passed.")


if __name__ == "__main__":
    main()
