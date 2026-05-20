"""WorldQuant BRAIN alpha research operations toolkit.

The package root intentionally keeps imports light.  Operational commands such
as the red-line verifier must not fail because an unrelated research subsystem
has an optional dependency missing from the current Python environment.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

__version__ = "0.3.0"


def _configure_logging() -> None:
    root = logging.getLogger()
    if any(getattr(handler, "_brain_alpha_ops_handler", False) for handler in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler.setLevel(logging.WARNING)
    handler._brain_alpha_ops_handler = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(logging.WARNING)


_configure_logging()


_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "JobStore": ("brain_alpha_ops.tasks", "JobStore"),
    "BrainAlphaToolbox": ("brain_alpha_ops.agent_tools", "BrainAlphaToolbox"),
    "ToolDefinition": ("brain_alpha_ops.agent_tools", "ToolDefinition"),
    "tool_definitions": ("brain_alpha_ops.agent_tools", "tool_definitions"),
    "OfficialDataLoader": ("brain_alpha_ops.data", "OfficialDataLoader"),
    "FieldDatasetMapper": ("brain_alpha_ops.data", "FieldDatasetMapper"),
    "OfficialField": ("brain_alpha_ops.data", "OfficialField"),
    "OfficialOperator": ("brain_alpha_ops.data", "OfficialOperator"),
    "OfficialDataset": ("brain_alpha_ops.data", "OfficialDataset"),
    "DatasetRef": ("brain_alpha_ops.data", "DatasetRef"),
    "CandidateGenerator": ("brain_alpha_ops.research", "CandidateGenerator"),
    "DynamicThemeEngine": ("brain_alpha_ops.research", "DynamicThemeEngine"),
    "DatasetSelector": ("brain_alpha_ops.research", "DatasetSelector"),
    "AlphaCheckRegistry": ("brain_alpha_ops.research", "AlphaCheckRegistry"),
    "AlphaTemplateRegistry": ("brain_alpha_ops.research", "AlphaTemplateRegistry"),
    "ResearchMemory": ("brain_alpha_ops.research", "ResearchMemory"),
}

__all__ = ["__version__", *_LAZY_EXPORTS]


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    module = importlib.import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
