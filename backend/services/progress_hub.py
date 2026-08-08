"""
services/progress_hub.py — Bus de progreso para WebSocket.

Mantiene suscriptores por "canal" (p. ej. session:12, run:abcd). Los servicios de
análisis/corrección publican eventos y el endpoint WebSocket los reenvía en vivo.
Guarda el último evento por canal para clientes que se conectan tarde.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any


class ProgressHub:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._last: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, channel: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        async with self._lock:
            self._subs[channel].add(q)
            if channel in self._last:
                q.put_nowait(self._last[channel])
        return q

    async def unsubscribe(self, channel: str, q: asyncio.Queue) -> None:
        async with self._lock:
            self._subs[channel].discard(q)
            if not self._subs[channel]:
                self._subs.pop(channel, None)

    async def publish(self, channel: str, event: dict[str, Any]) -> None:
        self._last[channel] = event
        async with self._lock:
            queues = list(self._subs.get(channel, set()))
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def publish_threadsafe(self, loop: asyncio.AbstractEventLoop,
                           channel: str, event: dict[str, Any]) -> None:
        """Para publicar desde un hilo (análisis en background con to_thread)."""
        asyncio.run_coroutine_threadsafe(self.publish(channel, event), loop)

    def last(self, channel: str) -> dict | None:
        return self._last.get(channel)


hub = ProgressHub()
