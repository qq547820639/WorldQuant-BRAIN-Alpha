"""Constants and data models for the final release readiness gate.

Split from the former ``scripts/final_release_gate.py`` monolith
(deep-optimization-phase12, Task A4). Holds the repo-root bootstrap, release
config/schema constants, official-API/dataset/context redline constants, and
the ``Finding`` / ``GateReport`` dataclasses shared across submodules.
"""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brain_alpha_ops.brain_api.canonical import CANONICAL_API_PATHS


DEFAULT_CONFIG = ROOT / "config" / "run_config.json"
SCHEMA_VERSION = "final_release_gate.v1"

REQUIRED_OFFICIAL_API: dict[str, str] = {
    "base_url": "https://api.worldquantbrain.com",
    "authentication_path": CANONICAL_API_PATHS["authentication"],
    "simulations_path": CANONICAL_API_PATHS["simulations"],
    "data_fields_path": CANONICAL_API_PATHS["data_fields"],
    "operators_path": CANONICAL_API_PATHS["operators"],
    "user_alphas_path": CANONICAL_API_PATHS["user_alphas"],
}

RELEASE_DATASET_STRATEGIES = {"fixed", "locked", "specific"}
LEGACY_SINGLE_DATASET_STRATEGIES = {"rotate"}
CUSTOM_EXTENSION_NAMES = ("custom_operator", "register_operator", "extend_operator", "custom_field", "register_field", "extend_field")
OFFICIAL_CONTEXT_FILES = ("official_fields.json", "official_operators.json", "official_datasets.json")
OFFICIAL_CONTEXT_REQUIRED_METADATA = ("complete", "schema_ok", "sha256_matches", "record_count_matches")


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    path: str | None = None
    current: Any | None = None
    expected: Any | None = None


@dataclass(frozen=True)
class GateReport:
    passed: bool
    schema_version: str
    config: str
    manifest_hash: str
    redlines: dict[str, bool]
    findings: list[Finding]
    official_context: dict[str, Any]
    implementation_tracker: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.passed, **asdict(self)}


def _add_finding(findings: list[Finding], *args: Any, **kwargs: Any) -> None:
    findings.append(Finding(*args, **kwargs))
