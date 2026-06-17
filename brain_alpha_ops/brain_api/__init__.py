"""BRAIN API adapters."""

__all__ = ["BrainAPI", "BrainAPIError", "OfficialBrainAPI"]


def __getattr__(name: str):
    if name in {"BrainAPI", "BrainAPIError"}:
        from .base import BrainAPI, BrainAPIError
        return {"BrainAPI": BrainAPI, "BrainAPIError": BrainAPIError}[name]
    if name == "OfficialBrainAPI":
        try:
            from .official import OfficialBrainAPI
            return OfficialBrainAPI
        except ImportError as exc:
            raise ImportError(
                f"Failed to import {name!r} from {__name__!r}: {exc}"
            ) from exc
    raise AttributeError(name)
