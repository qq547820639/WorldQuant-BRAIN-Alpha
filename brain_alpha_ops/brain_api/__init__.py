"""BRAIN API adapters."""

__all__ = ["OfficialBrainAPI"]


def __getattr__(name: str):
    if name == "OfficialBrainAPI":
        try:
            from .official import OfficialBrainAPI
            return OfficialBrainAPI
        except ImportError as exc:
            raise ImportError(
                f"Failed to import {name!r} from {__name__!r}: {exc}"
            ) from exc
    raise AttributeError(name)
