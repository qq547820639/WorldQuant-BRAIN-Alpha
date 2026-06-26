"""Path defaults and tracked-data category constants.

Split from the former ``scripts/check_tracked_data_inventory.py`` monolith
(Task A7 of deep-optimization-phase12). Holds the repository root, the
default boundary-plan path, the canonical boundary statuses, and the
prefix/path tuples that classify tracked data files into runtime-generated,
official snapshot, qualification snapshot, or review artifact buckets.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BOUNDARY_PLAN = ROOT / "docs" / "TRACKED_DATA_BOUNDARY_PLAN.json"
BOUNDARY_STATUSES = {"keep", "remove", "pending_decision"}

RUNTIME_GENERATED_PREFIXES = (
    "data/_codex_bench",
    "data/api_cache/",
    "data/checkpoints/",
    "data/e2e_screenshots/",
    "data/jobs_",
    "data/run_history/",
)
RUNTIME_GENERATED_PATHS = {
    "data/simulation_cooldown.json",
}
SNAPSHOT_PREFIXES = ("data/official_",)
QUALIFICATION_SNAPSHOT_PATHS = {"data/qualified_alpha_summary.json"}
REVIEW_ARTIFACT_PREFIXES = ("data/prd_", "data/qa_", "data/audit/")
REFERENCE_EXCLUDED_PREFIXES = ("data/", "tests/")
REFERENCE_EXCLUDED_PATHS = {
    ".gitignore",
    "docs/REVIEW_GAP_CLOSURE_20260530.md",
    "docs/TRACKED_DATA_BOUNDARY_PLAN.json",
    "scripts/check_tracked_data_inventory.py",
}
