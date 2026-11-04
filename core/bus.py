# core/bus.py
# Updated 2026-07-26 — error isolation between handlers. Jay Pratt + AI (Claude, Anthropic).

from typing import Callable, Dict, List

from core.logger import setup_agent_logger


class EventBus:
    """Single in-process pub/sub bus.

    One instance is created by the entry point and handed to every agent.
    Handlers are isolated: an exception in one subscriber is logged and the
    remaining subscribers still receive the event.
    """

    def __init__(self, name: str = "event_bus", log_publishes: bool = True):
        """log_publishes: whether publish() logs its generic
        per-publish line. Defaults to True -- unchanged behaviour for
        every existing caller. 2026-11-04: job2 constructs a fresh,
        throwaway EventBus per channel/setting/window combo, so this
        line fires once per reading there (Ccode update.txt, "JOB 2
        SPEED-UP"); only job2 passes False. Each agent's own specific
        event announcement (jump/level/leash/fault/CHESTER) is a
        separate self.logger.info() call on the AGENT, not this one --
        real events stay logged either way."""
        self.subscribers: Dict[str, List[Callable[[dict], None]]] = {}
        self.logger = setup_agent_logger(name)
        self._log_publishes = log_publishes

    def subscribe(self, topic: str, handler: Callable[[dict], None]):
        handler_name = getattr(handler, "__name__", repr(handler))
        self.logger.info(f"Subscribing to '{topic}' with handler '{handler_name}'")
        self.subscribers.setdefault(topic, []).append(handler)

    def unsubscribe(self, topic: str, handler: Callable[[dict], None]):
        handlers = self.subscribers.get(topic, [])
        if handler in handlers:
            handlers.remove(handler)

    def publish(self, topic: str, payload: dict):
        handlers = self.subscribers.get(topic, [])
        if self._log_publishes:
            self.logger.info(f"Publishing '{topic}' to {len(handlers)} handler(s): {payload}")
        for handler in list(handlers):
            try:
                handler(payload)
            except Exception:
                handler_name = getattr(handler, "__name__", repr(handler))
                self.logger.exception(
                    f"Handler '{handler_name}' raised while processing '{topic}'"
                )