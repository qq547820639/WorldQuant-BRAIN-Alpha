"""Runtime context facade for web console services."""

from __future__ import annotations

from ._allowed_names import WEB_CONTEXT_ALLOWED_NAMES


class WebApplicationContext:
    """Runtime context facade for web console services."""

    __slots__ = ("_module", "_allowed_names")

    def __init__(self, module, *, allowed_names=WEB_CONTEXT_ALLOWED_NAMES):
        object.__setattr__(self, "_module", module)
        object.__setattr__(self, "_allowed_names", frozenset(allowed_names))

    def __getattribute__(self, name: str):
        if name in {"_module", "_allowed_names"}:
            raise AttributeError(name)
        return object.__getattribute__(self, name)

    def __getattr__(self, name: str):
        allowed_names = object.__getattribute__(self, "_allowed_names")
        if name not in allowed_names:
            raise AttributeError(name)
        module = object.__getattribute__(self, "_module")
        return getattr(module, name)

    def __setattr__(self, name: str, value) -> None:
        allowed_names = object.__getattribute__(self, "_allowed_names")
        if name not in allowed_names:
            raise AttributeError(name)
        module = object.__getattribute__(self, "_module")
        setattr(module, name, value)
