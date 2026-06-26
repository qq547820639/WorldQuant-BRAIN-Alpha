"""Default paths and tracker contract constants.

Split from the former ``scripts/check_review_gap_closure_tracker.py`` monolith
(Task A3 of deep-optimization-phase12). Holds the path defaults, schema
identifier, and the literal section/snippet/checks/items tuples that define
the tracker document contract.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_review_gap_closure_tracker_helpers import (  # noqa: E402
    OFFICIAL_CONTEXT_QUEUE_ITEM,
    ADDITIONAL_TRIAGE_ITEMS as _ADDITIONAL_TRIAGE_ITEMS,
    ADDITIONAL_TRIAGE_SNIPPETS as _ADDITIONAL_TRIAGE_SNIPPETS,
)

DEFAULT_TRACKER = ROOT / "docs" / "REVIEW_GAP_CLOSURE_20260530.md"
DEFAULT_DELIVERY_AUDIT = ROOT / "docs" / "DELIVERY_COMPLETION_AUDIT_20260528.md"
DEFAULT_CONFIG = ROOT / "config" / "run_config.json"
DEFAULT_JOBS = ROOT / "data" / "jobs_production.json"
DEFAULT_REFRESH_STATUS = ROOT / "data" / "official_context_refresh_status.json"
DEFAULT_REACT_APP_DIR = ROOT / "brain_alpha_ops" / "web" / "react_app"
SCHEMA_VERSION = "review_gap_closure_tracker_check.v1"

REQUIRED_SECTIONS = (
    "Current Run Baseline",
    "2026-05-31 Delivery Review Triage",
    "Status Matrix",
    "Active Work Queue",
    "Not Yet Claimable",
)
BASELINE_SNIPPETS = (
    "quality_gate.py config validation",
    "scripts/check_frontend_surface_parity.py --json",
    "scripts/check_frontend_innerhtml.py --json",
    "document.writeln",
    "scripts/check_tracked_data_inventory.py --json",
    "scripts/check_react_build_env.py --json",
    "ready=true",
    "build_runner=local_node_modules",
    "scripts/check_live_submit_readiness.py --json",
    "scan_sensitive_artifacts.py --root . --json --fail-on-findings --include-all --include-git-history",
    "scripts/check_v5_defect_tracking.py --json",
)
BASELINE_CHECKS = (
    ("quality_gate.py config validation", ("PASS",)),
    ("scripts/check_frontend_surface_parity.py --json", ("PASS",)),
    ("scripts/check_frontend_innerhtml.py --json", ("PASS", "document.writeln", "trustedHtml", "createContextualFragment")),
    ("scripts/check_tracked_data_inventory.py --json", ("PASS",)),
    (
        "scripts/check_diagnostic_report.py --config config/run_config.json --report docs/ALPHA_PRODUCTION_DIAGNOSIS_20260522.md --json",
        ("PASS",),
    ),
    ("scripts/check_react_build_env.py --json", ("PASS", "ready=true", "build_runner=local_node_modules")),
    (
        "scripts/check_live_submit_readiness.py --json",
        ("PASS",),
    ),
    (
        "scripts/scan_sensitive_artifacts.py --root . --json --fail-on-findings --include-all --include-git-history",
        ("PASS", "findings=[]"),
    ),
    ("scripts/check_review_gap_closure_tracker.py --json", ("PASS", "tracker_contract_ok=true")),
    ("scripts/check_v5_defect_tracking.py --json", ("PASS", "required_validation_count=29", "findings=[]")),
)
TRIAGE_SNIPPETS = (
    "BRAIN_E2E_*",
    "data/e2e_screenshots/example.png",
    "--include-all --include-git-history",
    "output/` runtime smoke artifacts",
    "session-cookie-*",
    ".outerHTML",
    "trustedHtml",
    "createContextualFragment",
    "explicit allowlist",
    "BRAIN_PASSWORD",
    "OPENAI_API_KEY",
    "timeout=300",
    "exit_code=124",
    "launch_web.py --smoke-test --frontend react --port 0",
    "explicit `0`",
    "OS-assigned",
) + _ADDITIONAL_TRIAGE_SNIPPETS
TRIAGE_ITEMS = (
    ("Review P0 hardcoded E2E credentials", "CLOSED_CURRENT"),
    ("Review P0 E2E screenshot ignore policy", "CLOSED_CURRENT"),
    ("Review P0 CI secret scan coverage", "CLOSED_CURRENT"),
    ("Review P1 inline HTML injection risk", "CLOSED_CURRENT"),
    ("Review P1 quality-gate subprocess environment", "CLOSED_CURRENT"),
    ("Review P1 quality-gate subprocess timeout", "CLOSED_CURRENT"),
    ("Review P2 quality-gate preview smoke port race", "CLOSED_CURRENT"),
) + _ADDITIONAL_TRIAGE_ITEMS
STATUS_MATRIX_ITEMS = (
    ("P0-2 React strict build", "CLOSED_CURRENT"),
    ("P2-6 Frontend automated tests", "CLOSED_LOCAL_WITH_TOOLCHAIN"),
    ("P3-1 Dual frontend unification", "CLOSED_CURRENT"),
)
BASE_QUEUE_ITEMS: tuple[str, ...] = ()
FRONTEND_SURFACE_QUEUE_ITEM = "Frontend production-surface promotion"
NOT_YET_SNIPPETS = (
    "Real BRAIN submit success is not claimable",
    "non-blocking follow-up",
    "eligible_count=0",
    "ledger_eligible_count=0",
    "job_family_eligible_count=0",
)
DELIVERY_AUDIT_SNIPPETS = (
    "docs/REVIEW_GAP_CLOSURE_20260530.md",
    "ready=true",
    "build_runner=local_node_modules",
    "lockfile, `node_modules`, required packages, and the React artifact are present",
)
STALE_DELIVERY_AUDIT_SNIPPETS = (
    "ready=false",
    "missing `npm`, lockfile",
    "current default PATH still needs npm",
    "React strict-build reproducibility on the current default PATH is not claimable",
)
TRACKER_STALE_SNIPPETS = (
    "advisory only: `ready=false`",
    "missing `npm`",
    "npm is missing on the current PATH",
    "npm-enabled local toolchain path",
    "current default PATH still needs npm",
    "React strict-build reproducibility on the current default PATH is not claimable",
    "live BRAIN submit as the only active queue item",
    "Official context validation is fresh with `p1_findings=0`",
)
