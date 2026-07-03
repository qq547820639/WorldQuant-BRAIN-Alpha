"""LLM provider abstractions for the ``llm_review`` subpackage.

Includes the ``LLMProvider`` protocol, deterministic/fallback/router
providers, and the optional OpenAI-compatible Chat Completions adapter.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from brain_alpha_ops.redaction import redact_error_message

logger = logging.getLogger("brain_alpha_ops.research.llm_review")


class LLMProvider(Protocol):
    name: str

    def complete(self, request: dict[str, Any]) -> str:
        ...


@dataclass
class StaticLLMProvider:
    """Deterministic provider for tests and offline review flows."""

    response: str
    name: str = "static"

    def complete(self, request: dict[str, Any]) -> str:
        return self.response


class FallbackLLMProvider:
    """Try providers in order and return the first successful response."""

    name = "fallback"

    def __init__(self, providers: list[LLMProvider]):
        self.providers = [provider for provider in providers if provider is not None]

    def complete(self, request: dict[str, Any]) -> str:
        errors: list[str] = []
        for provider in self.providers:
            name = getattr(provider, "name", provider.__class__.__name__)
            try:
                return provider.complete(request)
            except Exception as exc:
                message = redact_error_message(exc, max_length=160)
                logger.warning(
                    "fallback LLM provider failed; trying next provider: provider=%s error=%s",
                    name,
                    message,
                )
                errors.append(f"{name}: {message}")
        raise RuntimeError("all LLM providers failed: " + "; ".join(errors or ["no providers configured"]))


class LLMProviderRouter:
    """Task-aware provider router with lightweight health tracking."""

    name = "router"

    def __init__(self, providers: list[LLMProvider], *, task_routes: dict[str, list[str]] | None = None):
        self.providers = [provider for provider in providers if provider is not None]
        self.task_routes = {str(key): list(value) for key, value in (task_routes or {}).items()}
        self.health: dict[str, dict[str, Any]] = {}

    def complete(self, request: dict[str, Any]) -> str:
        task = str(request.get("task") or "default")
        providers = self._providers_for_task(task)
        errors: list[str] = []
        for provider in providers:
            name = getattr(provider, "name", provider.__class__.__name__)
            started = time.perf_counter()
            try:
                output = provider.complete(request)
                self._record_health(name, ok=True, latency_seconds=time.perf_counter() - started)
                return output
            except Exception as exc:
                message = redact_error_message(exc, max_length=160)
                self._record_health(name, ok=False, latency_seconds=time.perf_counter() - started, error=message)
                logger.warning(
                    "routed LLM provider failed; trying next provider: provider=%s task=%s error=%s",
                    name,
                    task,
                    message,
                )
                errors.append(f"{name}: {message}")
        raise RuntimeError("all routed LLM providers failed: " + "; ".join(errors or ["no providers configured"]))

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": "llm_provider_router.v1",
            "provider_count": len(self.providers),
            "task_routes": dict(self.task_routes),
            "health": dict(self.health),
        }

    def _providers_for_task(self, task: str) -> list[LLMProvider]:
        names = self.task_routes.get(task) or self.task_routes.get("default") or []
        if not names:
            return list(self.providers)
        by_name = {getattr(provider, "name", provider.__class__.__name__): provider for provider in self.providers}
        routed = [by_name[name] for name in names if name in by_name]
        return routed or list(self.providers)

    def _record_health(self, name: str, *, ok: bool, latency_seconds: float, error: str = "") -> None:
        row = self.health.setdefault(name, {"ok_count": 0, "error_count": 0, "last_ok": False})
        row["last_ok"] = bool(ok)
        row["last_latency_seconds"] = round(max(0.0, latency_seconds), 3)
        if ok:
            row["ok_count"] = int(row.get("ok_count", 0)) + 1
            row["last_error"] = ""
        else:
            row["error_count"] = int(row.get("error_count", 0)) + 1
            row["last_error"] = error[:160]


class OpenAICompatibleProvider:
    """Minimal optional Chat Completions adapter.

    The project intentionally avoids a hard SDK dependency here.  Any provider
    exposing an OpenAI-compatible ``/chat/completions`` endpoint can be enabled
    through environment variables.
    """

    name = "openai_compatible"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        timeout_seconds: float = 60.0,
        transport: Any | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (base_url if base_url is not None else os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = model if model is not None else os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self.temperature = temperature
        self.timeout_seconds = max(1.0, float(timeout_seconds or 60.0))
        self.transport = transport or urllib.request.urlopen

    @classmethod
    def from_env(cls) -> "OpenAICompatibleProvider | None":
        if not os.environ.get("OPENAI_API_KEY"):
            return None
        return cls()

    def complete(self, request: dict[str, Any]) -> str:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAICompatibleProvider")
        payload = self._payload(request)
        http_request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self.transport(http_request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM provider HTTP {exc.code}: {body[:300]}") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"LLM provider request failed: {exc}") from exc
        choices = data.get("choices") if isinstance(data, dict) else None
        if not choices:
            raise RuntimeError("LLM provider returned no choices")
        message = (choices[0] or {}).get("message") if isinstance(choices[0], dict) else {}
        content = message.get("content") if isinstance(message, dict) else ""
        if not content:
            raise RuntimeError("LLM provider returned empty content")
        return str(content)

    def _payload(self, request: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": list(request.get("messages") or []),
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        response_schema = request.get("response_schema")
        if response_schema:
            payload["response_format"] = {"type": "json_object"}
        return payload


def _providers_from_env() -> list[LLMProvider]:
    providers: list[LLMProvider] = []
    primary = OpenAICompatibleProvider.from_env()
    if primary is not None:
        providers.append(primary)
    fallback_key = os.environ.get("OPENAI_FALLBACK_API_KEY", "")
    if fallback_key:
        providers.append(
            OpenAICompatibleProvider(
                api_key=fallback_key,
                base_url=os.environ.get("OPENAI_FALLBACK_BASE_URL", os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")),
                model=os.environ.get("OPENAI_FALLBACK_MODEL", os.environ.get("OPENAI_MODEL", "gpt-4o-mini")),
                temperature=_optional_float(os.environ.get("OPENAI_FALLBACK_TEMPERATURE")),
            )
        )
    return providers


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
