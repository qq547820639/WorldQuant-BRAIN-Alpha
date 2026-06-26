"""Path defaults and parity-plan status constants.

Split from the former ``scripts/check_frontend_surface_parity.py`` monolith
(Task A10 of deep-optimization-phase12). Holds the resolved project root,
default frontend source paths, and the allowed status sets used by the
parity-plan validators.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_INLINE_REGISTRY = ROOT / "brain_alpha_ops" / "web" / "js" / "view-registry.js"
DEFAULT_REACT_APP = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src" / "App.tsx"
DEFAULT_PARITY_PLAN = ROOT / "docs" / "FRONTEND_SURFACE_PARITY_PLAN.json"
VALID_PLAN_STATUSES = {"implemented", "planned", "retired"}
VALID_REACT_ONLY_STATUSES = {"accepted"}
