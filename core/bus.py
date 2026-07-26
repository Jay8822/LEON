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

    def __init__(self, name: str = "event_bus"):
        self.subscribers: Dict[str, List[Callable[[dict], None]]] = {}
        self.logger = setup_agent_logger(name)

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
        self.logger.info(f"Publishing '{topic}' to {len(handlers)} handler(s): {payload}")
        for handler in list(handlers):
            try:
                handler(payload)
            except Exception:
                handler_name = getattr(handler, "__name__", repr(handler))
                self.logger.exception(
                    f"Handler '{handler_name}' raised while processing '{topic}'"
                )