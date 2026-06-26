"""Validate production defect tracking evidence for the 2026-06-02 report.

The implementation has been split into the
``scripts.check_prod_defect_tracking`` subpackage (Task A6 of
deep-optimization-phase12). Submodules:

* ``_constants`` — schema version, default paths, required evidence snippets,
  expected thresholds / submission / generation config.
* ``_gate_invariants`` — readiness gate invariant probes and the ``_finding``
  helper shared across the package.
* ``_checker`` — main ``check_prod_defect_tracking`` validator and the report
  row / config / readiness helpers.
* ``_cli`` — argparse ``main`` entry point.
"""

from __future__ import annotations

from scripts.check_live_submit_readiness import check_live_submit_readiness

from ._checker import check_prod_defect_tracking
from ._cli import main
from ._constants import (
    DEFAULT_CONFIG,
    DEFAULT_JOBS,
    DEFAULT_REPORT,
    EXPECTED_GENERATION_CONFIG,
    EXPECTED_SUBMISSION_POLICY,
    EXPECTED_THRESHOLDS,
    REQUIRED_PROD_007_SNIPPETS,
    REQUIRED_PROD_012_SNIPPETS,
    REQUIRED_PROD_013_SNIPPETS,
    REQUIRED_PROD_014_SNIPPETS,
    REQUIRED_PROD_015_SNIPPETS,
    REQUIRED_PROD_016_SNIPPETS,
    REQUIRED_PROD_017_SNIPPETS,
    REQUIRED_PROD_018_SNIPPETS,
    REQUIRED_PROD_019_SNIPPETS,
    REQUIRED_PROD_020_SNIPPETS,
    REQUIRED_PROD_021_SNIPPETS,
    REQUIRED_PROD_022_SNIPPETS,
    REQUIRED_PROD_023_SNIPPETS,
    REQUIRED_PROD_024_SNIPPETS,
    REQUIRED_PROD_025_SNIPPETS,
    REQUIRED_PROD_IDS,
    REQUIRED_VALIDATION_SNIPPETS,
    ROOT,
    SCHEMA_VERSION,
)

__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_JOBS",
    "DEFAULT_REPORT",
    "EXPECTED_GENERATION_CONFIG",
    "EXPECTED_SUBMISSION_POLICY",
    "EXPECTED_THRESHOLDS",
    "REQUIRED_PROD_007_SNIPPETS",
    "REQUIRED_PROD_012_SNIPPETS",
    "REQUIRED_PROD_013_SNIPPETS",
    "REQUIRED_PROD_014_SNIPPETS",
    "REQUIRED_PROD_015_SNIPPETS",
    "REQUIRED_PROD_016_SNIPPETS",
    "REQUIRED_PROD_017_SNIPPETS",
    "REQUIRED_PROD_018_SNIPPETS",
    "REQUIRED_PROD_019_SNIPPETS",
    "REQUIRED_PROD_020_SNIPPETS",
    "REQUIRED_PROD_021_SNIPPETS",
    "REQUIRED_PROD_022_SNIPPETS",
    "REQUIRED_PROD_023_SNIPPETS",
    "REQUIRED_PROD_024_SNIPPETS",
    "REQUIRED_PROD_025_SNIPPETS",
    "REQUIRED_PROD_IDS",
    "REQUIRED_VALIDATION_SNIPPETS",
    "ROOT",
    "SCHEMA_VERSION",
    "check_live_submit_readiness",
    "check_prod_defect_tracking",
    "main",
]

if __name__ == "__main__":
    raise SystemExit(main())
