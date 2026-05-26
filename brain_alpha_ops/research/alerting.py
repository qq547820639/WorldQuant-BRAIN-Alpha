"""Simple external alert delivery helpers.

The default implementation is local-first and file/webhook friendly. It avoids
hard dependencies on any specific monitoring provider while still allowing the
stack to emit actionable alerts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any, Callable
from urllib import error, request


@dataclass
class AlertEvent:
    channel: str
    title: str
    message: str
    severity: str = "info"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "title": self.title,
            "message": self.message,
            "severity": self.severity,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }


class AlertDeliveryService:
    """Deliver alert events to file, webhook, or callback sinks."""

    def __init__(
        self,
        *,
        storage_dir: str | Path = "data",
        webhook_url: str = "",
        sender: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self.storage_dir = Path(storage_dir)
        self.webhook_url = webhook_url.strip()
        self.sender = sender
        self.alert_path = self.storage_dir / "alerts.jsonl"

    def alert(
        self,
        title: str,
        message: str,
        *,
        severity: str = "info",
        channel: str = "local",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_severity = _normalize_severity(severity)
        clean_channel = str(channel or "local").strip() or "local"
        event = AlertEvent(
            channel=clean_channel,
            title=title,
            message=message,
            severity=clean_severity,
            metadata=dict(metadata or {}),
        )
        payload = event.to_dict()
        persist_result = self._persist(payload)
        transport = self._deliver_webhook(payload)
        sender_result = {"delivered": False, "reason": "sender_not_configured"}
        if self.sender:
            try:
                self.sender(payload)
                sender_result = {"delivered": True}
            except Exception as exc:
                sender_result = {"delivered": False, "error": str(exc)}
        payload["transport"] = transport
        payload["sender"] = sender_result
        payload["persisted"] = persist_result
        payload["ok"] = bool(persist_result.get("persisted")) and not bool(transport.get("blocking_error")) and not bool(sender_result.get("blocking_error"))
        return payload

    def recent(self, limit: int = 50) -> dict[str, Any]:
        if not self.alert_path.is_file():
            return {
                "ok": True,
                "schema_version": "alert_log.v1",
                "count": 0,
                "alerts": [],
                "storage_dir": str(self.storage_dir),
            }
        rows: list[dict[str, Any]] = []
        for line in self.alert_path.read_text(encoding="utf-8").splitlines()[-max(1, int(limit or 1)) :]:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
        return {
            "ok": True,
            "schema_version": "alert_log.v1",
            "count": len(rows),
            "alerts": rows,
            "storage_dir": str(self.storage_dir),
        }

    def _persist(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            with self.alert_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            return {"persisted": True, "path": str(self.alert_path)}
        except OSError as exc:
            return {"persisted": False, "path": str(self.alert_path), "error": str(exc), "blocking_error": True}

    def _deliver_webhook(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.webhook_url:
            return {"delivered": False, "reason": "webhook_not_configured"}
        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = request.Request(self.webhook_url, data=data, headers={"Content-Type": "application/json"})
            with request.urlopen(req, timeout=5) as response:
                return {"delivered": True, "status": getattr(response, "status", 200)}
        except error.HTTPError as exc:
            return {"delivered": False, "status": exc.code, "error": str(exc), "blocking_error": exc.code >= 500}
        except Exception as exc:
            return {"delivered": False, "error": str(exc), "blocking_error": False}


class AlertRouter:
    """Route alerts through local, callback, and optional webhook transports."""

    def __init__(
        self,
        *,
        storage_dir: str | Path = "data",
        routes: dict[str, str] | None = None,
        sender: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self.storage_dir = Path(storage_dir)
        self.routes = dict(routes or {})
        self.sender = sender

    def route(
        self,
        title: str,
        message: str,
        *,
        severity: str = "info",
        channels: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        selected_channels = _unique_channels(channels or ["local"])
        deliveries = []
        for channel in selected_channels:
            webhook_url = self.routes.get(channel, "")
            delivery = AlertDeliveryService(
                storage_dir=self.storage_dir,
                webhook_url=webhook_url,
                sender=self.sender if channel == "callback" else None,
            ).alert(title, message, severity=severity, channel=channel, metadata=metadata)
            deliveries.append(delivery)
        failed = [item for item in deliveries if not _delivery_ok(item)]
        return {
            "ok": not failed,
            "schema_version": "alert_route_result.v1",
            "channel_count": len(selected_channels),
            "channels": selected_channels,
            "failed_count": len(failed),
            "deliveries": deliveries,
        }


def _unique_channels(channels: list[str]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for channel in channels:
        text = str(channel or "").strip() or "local"
        marker = text.lower()
        if marker in seen:
            continue
        seen.add(marker)
        rows.append(text)
    return rows


def _normalize_severity(value: str) -> str:
    text = str(value or "info").strip().lower()
    if text in {"debug", "info", "warning", "error", "critical"}:
        return text
    if text in {"warn", "medium"}:
        return "warning"
    if text in {"high", "fatal"}:
        return "critical"
    return "info"


def _delivery_ok(payload: dict[str, Any]) -> bool:
    if not payload.get("ok"):
        return False
    transport = payload.get("transport") if isinstance(payload.get("transport"), dict) else {}
    sender = payload.get("sender") if isinstance(payload.get("sender"), dict) else {}
    persisted = payload.get("persisted") if isinstance(payload.get("persisted"), dict) else {}
    return not any(
        bool(item.get("blocking_error"))
        for item in (transport, sender, persisted)
    )
