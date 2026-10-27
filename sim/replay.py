# sim/replay.py
# Added 2026-10-27 -- Jay Pratt + AI (Claude Sonnet 5, Anthropic).
"""Replays one sensor's full series through a real GracieAgent, same
one-channel-per-agent pattern every real-data test harness in this
project already uses (real_data_tests/esa_adb/run_esa_adb_test.py,
real_data_tests/opssat_ad/run_opssat_ad_test.py). No day-boundary
clear_fault() calls -- this sim is one continuous run, not a
multi-day recording.
"""
from core.bus import EventBus
from agents.gracie import GracieAgent


def replay_channel(channel, rule, timestamps, values, expected_windows=None):
    """expected_windows: optional list of (start_s, end_s) second-
    offsets (matching sim/craft.py's event start_s/end_s) during which
    this channel has an active expected cause. Returns a list of
    per-sample dicts: {sample_index, severity, jump_event,
    leash_settled, new_crossing_while_latched}."""
    expected_windows = expected_windows or []
    bus = EventBus()
    gracie = GracieAgent(bus, {channel: rule})
    log = []
    for i, (t, v) in enumerate(zip(timestamps, values)):
        second_offset = (t - timestamps[0]).total_seconds()
        expected = any(start <= second_offset < end for start, end in expected_windows)
        gracie.process_readings(
            {channel: v}, timestamp=t.timestamp(),
            expected_causes={channel} if expected else None,
        )
        last = gracie._last_readings[channel]
        log.append({
            "sample_index": i,
            "severity": last["severity"],
            "jump_event": bool(last["jump"]),
        })
    return log
