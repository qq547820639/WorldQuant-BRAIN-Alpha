"""Sensitive-artifact scanner subpackage.

Split from the former ``scan_sensitive_artifacts.py`` monolith (Workstream F3.9).
Public API is re-exported here so ``from scripts.scan_sensitive_artifacts import ...``
continues to resolve to the package directory (Python prefers the package
``__init__.py`` over the sibling ``scan_sensitive_artifacts.py`` shim when both
exist). The thin ``scripts/scan_sensitive_artifacts.py`` shim remains only to
preserve ``python scripts/scan_sensitive_artifacts.py`` direct invocation,
including the ``sys.path`` bootstrap for ``brain_alpha_ops``.
"""

from __future__ import annotations

from ._patterns import CRITICAL_CREDENTIAL_FILES
from ._scanners import (
    iter_candidate_files,
    main,
    scan_artifacts,
    scan_git_history,
)

__all__ = [
    "CRITICAL_CREDENTIAL_FILES",
    "iter_candidate_files",
    "main",
    "scan_artifacts",
    "scan_git_history",
]
