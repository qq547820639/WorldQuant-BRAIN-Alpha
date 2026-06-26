"""Composite WebHandlerDispatchContext aggregating all dispatch groups."""

from __future__ import annotations

from dataclasses import MISSING, dataclass, replace
from typing import Any

from ._groups import (
    WebDispatchActionContext,
    WebDispatchAssistantContext,
    WebDispatchConfigContext,
    WebDispatchCoreContext,
    WebDispatchJobContext,
    WebDispatchResearchContext,
    WebDispatchSessionContext,
    _CONTEXT_GROUPS,
    _GROUP_CLASSES,
)


@dataclass(frozen=True, init=False)
class WebHandlerDispatchContext:
    core: WebDispatchCoreContext
    session: WebDispatchSessionContext
    job: WebDispatchJobContext
    config: WebDispatchConfigContext
    research: WebDispatchResearchContext
    assistant: WebDispatchAssistantContext
    actions: WebDispatchActionContext

    def __init__(
        self,
        *,
        core: WebDispatchCoreContext | None = None,
        session: WebDispatchSessionContext | None = None,
        job: WebDispatchJobContext | None = None,
        config: WebDispatchConfigContext | None = None,
        research: WebDispatchResearchContext | None = None,
        assistant: WebDispatchAssistantContext | None = None,
        actions: WebDispatchActionContext | None = None,
        **flat: Any,
    ) -> None:
        provided = {
            "core": core,
            "session": session,
            "job": job,
            "config": config,
            "research": research,
            "assistant": assistant,
            "actions": actions,
        }
        remaining = dict(flat)
        for group_name, group in list(provided.items()):
            if group is not None and not isinstance(group, _GROUP_CLASSES[group_name]):
                remaining[group_name] = group
                provided[group_name] = None
        for group_name in _CONTEXT_GROUPS:
            group = provided[group_name]
            if group is None:
                group = _build_context_group(_GROUP_CLASSES[group_name], remaining)
            else:
                overrides = {}
                for field_name in _GROUP_CLASSES[group_name].__dataclass_fields__:
                    if field_name in remaining:
                        overrides[field_name] = remaining.pop(field_name)
                if overrides:
                    group = replace(group, **overrides)
            object.__setattr__(self, group_name, group)
        if remaining:
            unknown = ", ".join(sorted(remaining))
            raise TypeError(f"unknown WebHandlerDispatchContext fields: {unknown}")

    def __getattr__(self, name: str) -> Any:
        for group_name in _CONTEXT_GROUPS:
            group = object.__getattribute__(self, group_name)
            if name in getattr(group, "__dataclass_fields__", {}):
                return getattr(group, name)
        raise AttributeError(name)


def _build_context_group(group_class: type, values: dict[str, Any]) -> Any:
    fields = group_class.__dataclass_fields__
    payload = {}
    for name, field in fields.items():
        if name not in values:
            if field.default is not MISSING or field.default_factory is not MISSING:
                continue
            raise TypeError(f"missing WebHandlerDispatchContext field: {name}")
        payload[name] = values.pop(name)
    return group_class(**payload)
