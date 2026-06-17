"""Compatibility snapshot service exports.

The snapshot implementation was split across narrower web_* modules.  This
module keeps the old service import path available without duplicating logic.
"""

from __future__ import annotations

from typing import Any


def _call(name: str, *args: Any, **kwargs: Any) -> Any:
    from brain_alpha_ops import web_assistant_snapshots

    return getattr(web_assistant_snapshots, name)(*args, **kwargs)


def assistant_context_snapshot(*args: Any, **kwargs: Any) -> dict:
    return _call("assistant_context_snapshot", *args, **kwargs)


def assistant_guidance_history(*args: Any, **kwargs: Any) -> list[dict]:
    return _call("assistant_guidance_history", *args, **kwargs)


def assistant_guidance_snapshot(*args: Any, **kwargs: Any) -> dict:
    return _call("assistant_guidance_snapshot", *args, **kwargs)


def assistant_request_snapshot(*args: Any, **kwargs: Any) -> dict:
    return _call("assistant_request_snapshot", *args, **kwargs)


def assistant_response_guidance_payload(*args: Any, **kwargs: Any) -> dict:
    return _call("assistant_response_guidance_payload", *args, **kwargs)


def assistant_response_parse_payload(*args: Any, **kwargs: Any) -> dict:
    return _call("assistant_response_parse_payload", *args, **kwargs)


def durable_job_rows(*args: Any, **kwargs: Any) -> list[dict]:
    return _call("durable_job_rows", *args, **kwargs)


def latest_result_snapshot(*args: Any, **kwargs: Any) -> dict:
    return _call("latest_result_snapshot", *args, **kwargs)


def latest_run_history_path(*args: Any, **kwargs: Any):
    return _call("latest_run_history_path", *args, **kwargs)


def prompt_run_ledger_snapshot(*args: Any, **kwargs: Any) -> dict:
    return _call("prompt_run_ledger_snapshot", *args, **kwargs)


def research_knowledge_snapshot(*args: Any, **kwargs: Any) -> dict:
    return _call("research_knowledge_snapshot", *args, **kwargs)


def research_memory_snapshot(*args: Any, **kwargs: Any) -> dict:
    return _call("research_memory_snapshot", *args, **kwargs)


def research_observability_snapshot(*args: Any, **kwargs: Any) -> dict:
    return _call("research_observability_snapshot", *args, **kwargs)


def save_assistant_guidance_payload(*args: Any, **kwargs: Any) -> dict:
    return _call("save_assistant_guidance_payload", *args, **kwargs)


def user_profile_snapshot(*args: Any, **kwargs: Any) -> dict:
    return _call("user_profile_snapshot", *args, **kwargs)
