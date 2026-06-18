"""Config domain (v4.0) — runtime configuration, schema, validation, and hot-reload.

All config_*.py top-level modules are now accessible through this package.
Existing imports of `from brain_alpha_ops.config import ...` continue to work.
"""

from brain_alpha_ops.config._loader import (
    DEFAULT_RUN_CONFIG_PATH,
    ConfigValidationError,
    default_run_config_path,
    load_ops_config,
    load_run_config,
    resolve_default_dataset_id,
    resolve_runtime_path,
    runtime_project_root,
    validate_run_config,
    write_run_config,
)

# Re-export canonical enum validators for compliance verifier (RL-6)
from brain_alpha_ops.config_domain_validation import (
    _VALID_ALPHA_TYPES,
    _VALID_DELAYS,
    _VALID_NEUTRALIZATIONS,
    _VALID_ON_OFF,
    _VALID_REGIONS,
    _VALID_UNIT_HANDLING,
    _VALID_UNIVERSES,
)
from brain_alpha_ops.config_models import (
    BrainSettings,
    CredentialConfig,
    OfficialAPIConfig,
    OpsConfig,
    QualityThresholds,
    ResearchBudget,
    RunConfig,
    ScoringConfig,
    SubmissionPolicy,
    WebConfig,
)
from brain_alpha_ops.config_schema import (
    validate_config_file,
    validate_config_with_jsonschema,
)

