"""BRAIN API adapters."""

__all__ = ["OfficialBrainAPI"]


def __getattr__(name: str):
    if name == "OfficialBrainAPI":
        from .official import OfficialBrainAPI

        return OfficialBrainAPI
    raise AttributeError(name)
