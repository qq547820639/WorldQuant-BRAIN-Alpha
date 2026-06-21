"""Dataclass update helpers for configuration loading."""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import fields, is_dataclass
from typing import Any

from brain_alpha_ops.config_type_validation import (
    field_type_hint,
    type_hint_name,
    value_matches_type_hint,
)


def update_dataclass_from_mapping(
    instance: Any,
    data: dict[str, Any],
    *,
    path: str = "",
    error_cls: type[Exception] = ValueError,
    logger: logging.Logger | None = None,
) -> Any:
    if not isinstance(data, dict):
        return instance
    field_map = {item.name: item for item in fields(instance)}
    # P3-18 (2026-06-13): frozen dataclasses (ScoringConfig, QualityThresholds)
    # cannot be mutated in place.  Accumulate field updates in ``pending``
    # and emit a single ``dataclasses.replace`` once the loop is done.  The
    # returned instance is the new frozen object; the caller is responsible
    # for rebinding it (``setattr`` on the parent or reassignment).
    pending: dict[str, Any] = {}
    for key, value in data.items():
        if key not in field_map:
            if logger:
                logger.warning(
                    "unknown config key '%s' at %s — ignored; check for typos in config file",
                    key, path or "(root)",
                )
            continue
        item = field_map[key]
        current = getattr(instance, key)
        field_path = f"{path}.{key}" if path else key
        if is_dataclass(current) and isinstance(value, dict):
            new_child = update_dataclass_from_mapping(
                current,
                value,
                path=field_path,
                error_cls=error_cls,
                logger=logger,
            )
            if new_child is not current:
                pending[key] = new_child
        elif is_dataclass(current):
            if logger:
                logger.warning(
                    "invalid config type for %s: expected object, got %s",
                    field_path,
                    type(value).__name__,
                )
            raise error_cls(f"{field_path} must be an object")
        else:
            expected = field_type_hint(type(instance), item.name)
            if not value_matches_type_hint(value, expected):
                expected_name = type_hint_name(expected)
                if logger:
                    logger.warning(
                        "invalid config type for %s: expected %s, got %s",
                        field_path,
                        expected_name,
                        type(value).__name__,
                    )
                raise error_cls(
                    f"{field_path} has invalid type: expected {expected_name}, got {type(value).__name__}"
                )
            pending[key] = value
    if pending:
        try:
            new_instance = dataclasses.replace(instance, **pending)
        except (dataclasses.FrozenInstanceError, AttributeError, TypeError):
            # Fall back to in-place mutation for non-frozen dataclasses.
            for key, value in pending.items():
                setattr(instance, key, value)
            new_instance = instance
        return new_instance
    return instance
