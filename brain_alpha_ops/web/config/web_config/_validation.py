"""Settings enum validation."""
from __future__ import annotations

from brain_alpha_ops.web.config.web_config._constants import (
    _VALID_DELAYS,
    _VALID_NEUTRALIZATIONS,
    _VALID_REGIONS,
    _VALID_TYPES,
    _VALID_UNIVERSES,
)


def validate_settings_enums(settings: dict) -> None:
    """Raise ValueError if any settings field has an invalid enum value."""

    errors = []
    region = str(settings.get("region", "")).strip()
    if region and region not in _VALID_REGIONS:
        errors.append(f"Invalid region: '{region}'. Valid: {sorted(_VALID_REGIONS)}")
    universe = str(settings.get("universe", "")).strip()
    if universe and universe not in _VALID_UNIVERSES:
        errors.append(f"Invalid universe: '{universe}'. Valid: {sorted(_VALID_UNIVERSES)}")
    if "delay" in settings:
        try:
            delay = int(str(settings.get("delay")))
        except (TypeError, ValueError):
            errors.append(f"Invalid delay: '{settings.get('delay')}'. Valid: {sorted(_VALID_DELAYS)}")
        else:
            if delay not in _VALID_DELAYS:
                errors.append(f"Invalid delay: '{delay}'. Valid: {sorted(_VALID_DELAYS)}")
    neutralization = str(settings.get("neutralization", "")).strip()
    if neutralization and neutralization not in _VALID_NEUTRALIZATIONS:
        errors.append(f"Invalid neutralization: '{neutralization}'. Valid: {sorted(_VALID_NEUTRALIZATIONS)}")
    alpha_type = str(settings.get("type", settings.get("alphaType", ""))).strip()
    if alpha_type and alpha_type not in _VALID_TYPES:
        errors.append(f"Invalid alpha type: '{alpha_type}'. Valid: {sorted(_VALID_TYPES)}")
    if errors:
        raise ValueError("; ".join(errors))
