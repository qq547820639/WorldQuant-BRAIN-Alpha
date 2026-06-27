"""Private helpers extracted from config_domain_validation to satisfy the 350-line limit.

Holds the domain validation constant table and the credentials validators so that
``brain_alpha_ops.config_domain_validation`` stays within the project line budget. All
symbols are re-imported by the parent module, preserving the public API surface.
"""

from __future__ import annotations

import os

from brain_alpha_ops.brain_api.canonical import (
    SUPPORTED_ALPHA_TYPES,
    SUPPORTED_DELAYS,
    SUPPORTED_NEUTRALIZATIONS,
    SUPPORTED_PASTEURIZATION,
    SUPPORTED_REGIONS,
    SUPPORTED_UNIT_HANDLING,
    SUPPORTED_UNIVERSES,
)
from brain_alpha_ops.config_models import CredentialConfig
from brain_alpha_ops.config_validation_helpers import require_str

_VALID_ENVIRONMENT = "production"
_VALID_REGIONS = SUPPORTED_REGIONS
_VALID_UNIVERSES = SUPPORTED_UNIVERSES
_VALID_DELAYS = SUPPORTED_DELAYS
_VALID_NEUTRALIZATIONS = SUPPORTED_NEUTRALIZATIONS
_VALID_ALPHA_TYPES = SUPPORTED_ALPHA_TYPES
_VALID_DATASET_STRATEGIES = {"all", "rotate", "random", "specific", "fixed", "locked"}
_VALID_MARKET_REGIMES = {"normal", "low_vol", "high_vol"}
_VALID_ON_OFF = SUPPORTED_PASTEURIZATION
_VALID_UNIT_HANDLING = SUPPORTED_UNIT_HANDLING


def validate_credentials(
    errors: list[str],
    credentials: CredentialConfig,
    *,
    allow_plaintext: bool = False,
) -> None:
    if not isinstance(credentials, CredentialConfig):
        errors.append("credentials must be an object")
        return
    for field_name in ("username", "password", "token", "username_env", "password_env", "token_env"):
        require_str(errors, f"credentials.{field_name}", getattr(credentials, field_name))
    _reject_plaintext_credentials(errors, credentials, allow_plaintext=allow_plaintext)


def _reject_plaintext_credentials(
    errors: list[str],
    credentials: CredentialConfig,
    *,
    allow_plaintext: bool = False,
) -> None:
    """Reject non-empty plaintext credentials unless BRAIN_ALLOW_PLAINTEXT_CREDENTIALS is set.

    ``allow_plaintext`` lets in-memory, non-persisted flows (e.g. test_connection)
    accept page-entered credentials without weakening the persistence guard.
    """
    if allow_plaintext or os.environ.get("BRAIN_ALLOW_PLAINTEXT_CREDENTIALS"):
        return
    for field_name in ("username", "password", "token"):
        value = getattr(credentials, field_name)
        if value:
            errors.append(
                f"credentials.{field_name} contains a non-empty plaintext value; "
                "set it via the *_env field and environment variable instead, "
                "or set BRAIN_ALLOW_PLAINTEXT_CREDENTIALS=1 to override"
            )
