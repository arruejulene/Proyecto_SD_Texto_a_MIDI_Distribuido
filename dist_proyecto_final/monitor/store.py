from __future__ import annotations

from collections import deque
from datetime import datetime
from threading import Lock
from typing import Any


class MonitorStore:
    def __init__(self, max_events: int = 800) -> None:
        self.max_events = max_events
        self.events = deque(maxlen=max_events)
        self.status_by_processor: dict[str, dict[str, Any]] = {}
        self.delivery_by_id: dict[str, str] = {}
        self.lock = Lock()
        self._event_id_counter = 0

    def add_event(self, event: dict[str, Any]) -> None:
        enriched = {
            "ts": datetime.now().strftime("%H:%M:%S"),
            **event,
        }
        with self.lock:
            enriched["_id"] = self._event_id_counter
            self._event_id_counter += 1
            self.events.appendleft(enriched)
            processor = enriched.get("processor") or enriched.get("from")
            if processor:
                self.status_by_processor[str(processor)] = enriched
            message_id = enriched.get("message_id")
            if message_id:
                self.delivery_by_id[str(message_id)] = str(enriched.get("command") or enriched.get("type") or "EVENT")

    def push_system(self, message: str, **extra: Any) -> None:
        self.add_event({"command": "SYSTEM", "processor": "director", "message": message, **extra})

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "events": list(self.events),
                "processors": dict(self.status_by_processor),
                "delivery_count": len(self.delivery_by_id),
            }
