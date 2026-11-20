"""NEXUS Async Event Manager with Monotonic Sequence & History Buffer."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import itertools
from typing import Any
import uuid


@dataclass(slots=True)
class NexusEvent:
    sequence: int
    topic: str
    source: str
    timestamp: str
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "topic": self.topic,
            "source": self.source,
            "timestamp": self.timestamp,
            "data": self.data,
        }


class EventManager:
    """In-process async event bus bridging daemon subsystems and WebSocket subscribers."""

    def __init__(self, history_limit: int = 200) -> None:
        self._sequence = 0
        self._history: deque[NexusEvent] = deque(maxlen=history_limit)
        self._subscribers: dict[str, tuple[asyncio.Queue[NexusEvent], set[str] | None]] = {}
        self._lock = asyncio.Lock()

    async def publish(
        self,
        topic: str,
        source: str,
        data: dict[str, Any] | None = None,
    ) -> NexusEvent:
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            self._sequence += 1
            event = NexusEvent(
                sequence=self._sequence,
                topic=topic,
                source=source,
                timestamp=now,
                data=data or {},
            )
            self._history.append(event)
            for queue, topic_filter in self._subscribers.values():
                if topic_filter is None or topic in topic_filter:
                    if queue.full():
                        try:
                            queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    queue.put_nowait(event)
            return event

    async def subscribe(
        self, topics: set[str] | None = None, max_queue_size: int = 100
    ) -> tuple[str, asyncio.Queue[NexusEvent]]:
        sub_id = uuid.uuid4().hex
        queue: asyncio.Queue[NexusEvent] = asyncio.Queue(maxsize=max_queue_size)
        async with self._lock:
            self._subscribers[sub_id] = (queue, topics)
        return sub_id, queue

    async def unsubscribe(self, subscriber_id: str) -> None:
        async with self._lock:
            self._subscribers.pop(subscriber_id, None)

    def recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        return [e.to_dict() for e in itertools.islice(reversed(self._history), limit)]

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
