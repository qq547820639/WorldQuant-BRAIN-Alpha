"""BRAIN API adapters."""

__all__ = ["MockBrainAPI", "OfficialBrainAPI"]


def __getattr__(name: str):
    if name == "MockBrainAPI":
        from .mock import MockBrainAPI

        return MockBrainAPI
    if name == "OfficialBrainAPI":
        from .official import OfficialBrainAPI

        return OfficialBrainAPI
    raise AttributeError(name)
