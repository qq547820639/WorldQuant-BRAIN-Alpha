"""WebSocket handler — real-time bidirectional communication (ADR-004, v4.1).

Provides WebSocketManager for pub/sub across modules.
HTTP upgrade detection happens in web_http_handler.py.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Type alias for the message-send callback
MessageSender = Callable[[str], None]


class WebSocketManager:
    """Manages WebSocket clients and channel-based pub/sub.

    Thread-safe. One instance per worker process.
    """

    def __init__(self):
        self._subscribers: dict[str, set[MessageSender]] = {}
        self._connections: set[MessageSender] = set()
        self._lock = threading.Lock()

    # ── Connection Lifecycle ────────────────────────────────

    def connect(self, sender: MessageSender) -> None:
        """Register a new WebSocket connection."""
        with self._lock:
            self._connections.add(sender)

    def disconnect(self, sender: MessageSender) -> None:
        """Remove a WebSocket connection and all its subscriptions."""
        with self._lock:
            self._connections.discard(sender)
            for subscribers in self._subscribers.values():
                subscribers.discard(sender)

    # ── Pub/Sub ─────────────────────────────────────────────

    def subscribe(self, channel: str, sender: MessageSender) -> None:
        """Subscribe a connection to a channel."""
        with self._lock:
            self._subscribers.setdefault(channel, set()).add(sender)

    def unsubscribe(self, channel: str, sender: MessageSender) -> None:
        """Unsubscribe a connection from a channel."""
        with self._lock:
            subscribers = self._subscribers.get(channel)
            if subscribers:
                subscribers.discard(sender)

    def publish(self, channel: str, data: dict[str, Any]) -> None:
        """Publish a message to all subscribers of a channel."""
        with self._lock:
            subscribers = list(self._subscribers.get(channel, set()))
        if not subscribers:
            return
        message = json.dumps({
            "type": channel,
            "data": data,
            "timestamp": _utc_now_iso(),
        }, default=str)
        for sender in subscribers:
            try:
                sender(message)
            except Exception:
                logger.debug("ws publish to subscriber failed for channel=%s", channel, exc_info=True)

    # ── Query ───────────────────────────────────────────────

    @property
    def connection_count(self) -> int:
        with self._lock:
            return len(self._connections)

    def get_subscribers(self, channel: str) -> int:
        with self._lock:
            return len(self._subscribers.get(channel, set()))


# ── Helpers ─────────────────────────────────────────────────

def _utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ── Singleton ───────────────────────────────────────────────

ws_manager = WebSocketManager()
