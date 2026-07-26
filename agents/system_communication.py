# agents/system_communication.py
# Updated 2026-07-26 — replaced the old standalone event bus with this deprecated shim. Jay Pratt + AI (Claude, Anthropic).
"""Deprecated shim.

This module used to define a second, global event bus (``SimpleEventBus``)
alongside ``core.bus.EventBus``. Agents were split across the two, so events
published by one half were never seen by the other. There is now a single
``EventBus``, created by the entry point and passed to each agent.

Kept only so older scripts importing ``event_bus`` still import cleanly.
New code should accept a bus in its constructor instead.
"""

import warnings

from core.bus import EventBus

# Backwards-compatible alias.
SimpleEventBus = EventBus

# A standalone bus for legacy scripts. Nothing in the running system
# subscribes to it, so publishing here reaches no agent.
event_bus = EventBus("legacy_event_bus")

warnings.warn(
    "agents.system_communication.event_bus is deprecated; pass a core.bus.EventBus "
    "instance to each agent instead.",
    DeprecationWarning,
    stacklevel=2,
)