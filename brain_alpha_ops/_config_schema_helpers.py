"""Private schema-validation helpers split out of ``config_schema``.

These internals back the dependency-free fallback validator and the
partial-schema flattener used by ``validate_config_with_jsonschema``.  They
are re-exported from ``brain_alpha_ops.config_schema`` so the public API and
test monkeypatch surface (which patches ``config_schema.jsonschema``) remain
unchanged.

``RUN_CONFIG_SCHEMA`` is imported from ``config_schema`` for the identity
check used by the fallback; ``config_schema`` in turn imports these helpers
*after* ``RUN_CONFIG_SCHEMA`` is defined, so the module-load ordering is
safe.
"""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.config_schema import RUN_CONFIG_SCHEMA


def _validate_config_without_jsonschema(
    config_data: dict[str, Any],
    schema: dict[str, Any],
) -> list[str]:
    """Small dependency-free fallback for the schema subset used in tests.

    The production path prefers ``jsonschema``.  This fallback keeps critical
    type/enum/range checks active in minimal runtime environments.

    ``run_config.json`` is allowed to be a partial override file because
    ``load_run_config`` merges it into ``RunConfig()`` defaults before the
    procedural validator runs.  The fallback therefore treats the default run
    config schema as partial-friendly: an entirely empty object is still
    reported as missing required roots, while non-empty partial documents only
    validate fields that are explicitly present.
    """
    errors: list[str] = []
    enforce_required = schema is not RUN_CONFIG_SCHEMA or not config_data

    def path_label(path: tuple[str, ...]) -> str:
        return ".".join(path) if path else "(root)"

    def validate_node(value: Any, node_schema: dict[str, Any], path: tuple[str, ...]) -> None:
        expected_type = node_schema.get("type")
        if expected_type == "object":
            if not isinstance(value, dict):
                errors.append(f"{path_label(path)}: {value!r} is not an object")
                return
            if enforce_required:
                for key in node_schema.get("required", []):
                    if key not in value:
                        errors.append(f"{path_label(path)}: missing required property '{key}'")
            for key, child_schema in node_schema.get("properties", {}).items():
                if key in value and isinstance(child_schema, dict):
                    validate_node(value[key], child_schema, (*path, str(key)))
            return

        if expected_type == "string":
            if not isinstance(value, str):
                errors.append(f"{path_label(path)}: {value!r} is not a string")
                return
            min_length = node_schema.get("minLength")
            if isinstance(min_length, int) and len(value) < min_length:
                errors.append(
                    f"{path_label(path)}: {value!r} is shorter than the minimum length of {min_length}"
                )
        elif expected_type == "boolean":
            if not isinstance(value, bool):
                errors.append(f"{path_label(path)}: {value!r} is not a boolean")
                return
        elif expected_type == "integer":
            # NOTE: isinstance(True, int) is True in Python, so the bool check
            # MUST come before the int check. If the two checks are reordered,
            # booleans will silently pass as integers (1/0). Keep this order.
            if isinstance(value, bool) or not isinstance(value, int):
                errors.append(f"{path_label(path)}: {value!r} is not an integer")
                return
        elif expected_type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(f"{path_label(path)}: {value!r} is not a number")
                return

        allowed_values = node_schema.get("enum")
        if allowed_values is not None and value not in allowed_values:
            errors.append(f"{path_label(path)}: {value!r} is not one of {allowed_values!r}")

        if expected_type in {"integer", "number"}:
            numeric = float(value)
            minimum = node_schema.get("minimum")
            maximum = node_schema.get("maximum")
            if minimum is not None and numeric < float(minimum):
                errors.append(f"{path_label(path)}: {value!r} is less than the minimum of {minimum}")
            if maximum is not None and numeric > float(maximum):
                errors.append(f"{path_label(path)}: {value!r} is greater than the maximum of {maximum}")

    validate_node(config_data, schema, ())

    return errors


def _partial_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``schema`` that validates explicit override fields only."""
    cloned = dict(schema)
    cloned.pop("required", None)
    properties = cloned.get("properties")
    if isinstance(properties, dict):
        cloned["properties"] = {
            key: _partial_schema(value) if isinstance(value, dict) else value
            for key, value in properties.items()
        }
    return cloned
