"""WorldQuant BRAIN alpha research operations toolkit."""
import logging

from .tasks import JobStore
from .agent_tools import BrainAlphaToolbox, ToolDefinition, tool_definitions

# ── P2: Centralized logging configuration ──
_log_format = logging.Formatter(
    "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_log_handler = logging.StreamHandler()
_log_handler.setFormatter(_log_format)
_log_handler.setLevel(logging.WARNING)  # Default: WARNING+; set to DEBUG for development
logging.root.addHandler(_log_handler)
logging.root.setLevel(logging.WARNING)

from .data import OfficialDataLoader, FieldDatasetMapper, OfficialField, OfficialOperator, OfficialDataset, DatasetRef
from .research import (
    CandidateGenerator,
    DynamicThemeEngine,
    DatasetSelector,
    AlphaCheckRegistry,
    AlphaTemplateRegistry,
    ResearchMemory,
)

__version__ = "0.3.0"  # Quality v3: diagnostics, experience, margin, dataset wiring, BRAIN-aligned thresholds
