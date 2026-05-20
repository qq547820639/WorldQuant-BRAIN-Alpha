"""Provider-neutral LLM cross-review helpers."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
from typing import Any, Protocol

from brain_alpha_ops.models import utc_now
from brain_alpha_ops.redaction import redact_data, redact_error_message
from brain_alpha_ops.research.assistant import AssistantResponseParseError, parse_assistant_response


CROSS_REVIEW_SCHEMA_VERSION = "assistant_cross_review.v1"
PROMPT_RUN_LEDGER_SCHEMA_VERSION = "prompt_run_ledger.v1"


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
            try:
                return provider.complete(request)
            except Exception as exc:
                errors.append(f"{getattr(provider, 'name', provider.__class__.__name__)}: {str(exc)[:160]}")
        raise RuntimeError("all LLM providers failed: " + "; ".join(errors or ["no providers configured"]))


class LLMProviderRouter:
    """Task-aware provider router with lightweight health tracking."""

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
        payload = {
            "model": self.model,
            "messages": list(request.get("messages") or []),
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        response_schema = request.get("response_schema")
        if response_schema:
            payload["response_format"] = {"type": "json_object"}
        return payload


class CrossReviewService:
    """Review a primary assistant response against the original request pack."""

    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider

    def review(
        self,
        request_pack: dict[str, Any],
        primary_response: str | dict[str, Any],
        *,
        reviewer_response: str | dict[str, Any] | None = None,
        min_confidence: float = 0.6,
    ) -> dict[str, Any]:
        primary = _parse_response(primary_response, label="primary")
        raw_reviewer = reviewer_response
        if raw_reviewer is None:
            if self.provider is None:
                raw_reviewer = _offline_reviewer_response(primary, request_pack)
            else:
                raw_reviewer = self.provider.complete(_review_request(request_pack, primary))
        reviewer = _parse_response(raw_reviewer, label="reviewer")
        primary_confidence = _confidence(primary)
        reviewer_confidence = _confidence(reviewer)
        agreement = _agreement(primary, reviewer)
        conservative = (not agreement) or primary_confidence < min_confidence or reviewer_confidence < min_confidence
        decision = "accept" if agreement and not conservative else "conservative_review_required"
        result = {
            "ok": True,
            "schema_version": CROSS_REVIEW_SCHEMA_VERSION,
            "decision": decision,
            "agreement": agreement,
            "conservative": conservative,
            "min_confidence": min_confidence,
            "primary_confidence": primary_confidence,
            "reviewer_confidence": reviewer_confidence,
            "primary_digest": _digest_json(primary),
            "reviewer_digest": _digest_json(reviewer),
            "request_digest": str(request_pack.get("prompt_digest") or _digest_json(request_pack)),
            "primary": primary,
            "reviewer": reviewer,
            "risk_flags": sorted(set(_strings(primary.get("risk_flags")) + _strings(reviewer.get("risk_flags")))),
        }
        return redact_data(result)


class PromptRunLedger:
    """Append-only prompt run ledger that never stores provider secrets."""

    def __init__(self, storage_dir: str | Path):
        self.path = Path(storage_dir) / "prompt_runs.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        request_pack: dict[str, Any],
        model: str = "",
        temperature: float | None = None,
        response_text: str = "",
        parse_status: str = "",
    ) -> dict[str, Any]:
        row = redact_data(
            {
                "schema_version": PROMPT_RUN_LEDGER_SCHEMA_VERSION,
                "timestamp": utc_now(),
                "prompt_digest": request_pack.get("prompt_digest") or _digest_text(str(request_pack.get("prompt") or "")),
                "context_digest": request_pack.get("context_digest") or _digest_json(request_pack.get("context_pack") or {}),
                "model": model,
                "temperature": temperature,
                "response_digest": _digest_text(response_text),
                "parse_status": parse_status or "unknown",
            }
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
        return row


def cross_review_assistant_response(
    request_pack: dict[str, Any],
    primary_response: str | dict[str, Any],
    *,
    reviewer_response: str | dict[str, Any] | None = None,
    min_confidence: float = 0.6,
) -> dict[str, Any]:
    providers = _providers_from_env()
    provider = LLMProviderRouter(providers, task_routes={"cross_review": [getattr(provider, "name", provider.__class__.__name__) for provider in providers]}) if len(providers) > 1 else (providers[0] if providers else None)
    return CrossReviewService(provider).review(
        request_pack,
        primary_response,
        reviewer_response=reviewer_response,
        min_confidence=min_confidence,
    )


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


def _review_request(request_pack: dict[str, Any], primary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": "cross_review",
        "messages": [
            {"role": "system", "content": "Review the primary quant assistant response. Return one JSON object only."},
            {"role": "user", "content": json.dumps({"request": request_pack, "primary": primary}, ensure_ascii=False, default=str)},
        ],
        "response_schema": request_pack.get("request", {}).get("response_schema", {}),
    }


def _offline_reviewer_response(primary: dict[str, Any], request_pack: dict[str, Any]) -> dict[str, Any]:
    confidence = min(0.8, max(0.0, _confidence(primary)))
    risks = _strings(primary.get("risk_flags"))
    if not risks and "cloud" in json.dumps(request_pack, ensure_ascii=False, default=str).lower():
        risks.append("verify_cloud_cache_freshness")
    return {
        "summary": "Offline reviewer found no contradictory evidence in the supplied request pack.",
        "recommended_next_actions": _strings(primary.get("recommended_next_actions"))[:5],
        "risk_flags": risks,
        "candidate_adjustments": primary.get("candidate_adjustments") if isinstance(primary.get("candidate_adjustments"), list) else [],
        "follow_up_questions": [],
        "confidence": confidence,
    }


def _parse_response(value: str | dict[str, Any] | None, *, label: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        return parse_assistant_response(str(value or ""))
    except AssistantResponseParseError as exc:
        raise AssistantResponseParseError(f"{label} response parse failed: {exc}") from exc


def _agreement(primary: dict[str, Any], reviewer: dict[str, Any]) -> bool:
    primary_actions = set(_strings(primary.get("recommended_next_actions")))
    reviewer_actions = set(_strings(reviewer.get("recommended_next_actions")))
    primary_risks = set(_strings(primary.get("risk_flags")))
    reviewer_risks = set(_strings(reviewer.get("risk_flags")))
    if primary_risks and reviewer_risks and primary_risks.isdisjoint(reviewer_risks):
        return False
    if primary_actions and reviewer_actions and primary_actions.isdisjoint(reviewer_actions):
        return False
    return True


def _confidence(value: dict[str, Any]) -> float:
    try:
        number = float(value.get("confidence", 0.0))
    except (TypeError, ValueError):
        number = 0.0
    return max(0.0, min(1.0, number))


def _strings(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _digest_json(value: Any) -> str:
    return _digest_text(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def _digest_text(value: str) -> str:
    return sha256(str(value or "").encode("utf-8", errors="ignore")).hexdigest()[:16]


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
