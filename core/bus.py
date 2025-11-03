# core/bus.py

from typing import Callable, Dict, List

class EventBus:
    def __init__(self):
        self.subscribers: Dict[str, List[Callable[[dict], None]]] = {}

    def subscribe(self, topic: str, handler: Callable[[dict], None]):
        self.subscribers.setdefault(topic, []).append(handler)

    def publish(self, topic: str, payload: dict):
        for handler in self.subscribers.get(topic, []):
            handler(payload)
