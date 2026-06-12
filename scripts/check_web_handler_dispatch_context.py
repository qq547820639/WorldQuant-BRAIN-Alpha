"""Validate the grouped WebHandlerDispatchContext contract."""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import json
from typing import Any


DEFAULT_MODULE = "brain_alpha_ops.web_handler_dispatch"
SCHEMA_VERSION = "web_handler_dispatch_context_check.v1"
MAX_GROUP_FIELD_COUNT = 20
GROUP_CLASS_NAMES = {
    "core": "WebDispatchCoreContext",
    "session": "WebDispatchSessionContext",
    "job": "WebDispatchJobContext",
    "config": "WebDispatchConfigContext",
    "research": "WebDispatchResearchContext",
    "assistant": "WebDispatchAssistantContext",
    "actions": "WebDispatchActionContext",
}


def check_web_handler_dispatch_context(module_name: str = DEFAULT_MODULE) -> dict[str, Any]:
    module = importlib.import_module(module_name)
    findings: list[dict[str, str]] = []

    context_class = getattr(module, "WebHandlerDispatchContext")
    top_level_field_names = [field.name for field in dataclasses.fields(context_class)]
    group_classes = {
        group_name: getattr(module, class_name)
        for group_name, class_name in GROUP_CLASS_NAMES.items()
    }
    group_field_names: dict[str, list[str]] = {}
    duplicate_field_names: list[dict[str, str]] = []
    seen_fields: dict[str, str] = {}
    flat_kwargs: dict[str, Any] = {}
    grouped_kwargs: dict[str, Any] = {}

    if top_level_field_names != list(GROUP_CLASS_NAMES):
        findings.append(
            _finding(
                "top_level_field_names",
                ", ".join(top_level_field_names),
                "top-level context should be split into the expected group dataclasses",
            )
        )

    for group_name, group_class in group_classes.items():
        if not dataclasses.is_dataclass(group_class):
            findings.append(
                _finding(
                    "missing_group_dataclass",
                    group_class.__name__,
                    f"{group_name} context is not a dataclass",
                )
            )
            continue

        names = [field.name for field in dataclasses.fields(group_class)]
        group_field_names[group_name] = names
        if len(names) > MAX_GROUP_FIELD_COUNT:
            findings.append(
                _finding(
                    "group_field_count",
                    f"{group_name}:{len(names)}",
                    "grouped context should stay narrow enough for handler-specific dependencies",
                )
            )

        grouped_kwargs[group_name] = {}
        for field_name in names:
            value = object()
            flat_kwargs[field_name] = value
            grouped_kwargs[group_name][field_name] = value
            if field_name in seen_fields:
                duplicate_field_names.append(
                    {"name": field_name, "first_group": seen_fields[field_name], "second_group": group_name}
                )
            else:
                seen_fields[field_name] = group_name

    if duplicate_field_names:
        findings.append(
            _finding(
                "duplicate_field_names",
                ", ".join(sorted(item["name"] for item in duplicate_field_names)),
                "grouped contexts should not reuse the same dependency name in more than one group",
            )
        )

    flat_context = None
    grouped_context = None
    try:
        flat_context = context_class(**flat_kwargs)
    except Exception as exc:  # pragma: no cover - defensive guard path
        findings.append(_finding("flat_constructor_error", type(exc).__name__, str(exc)))

    try:
        grouped_context = context_class(
            **{group_name: group_classes[group_name](**grouped_kwargs[group_name]) for group_name in group_classes}
        )
    except Exception as exc:  # pragma: no cover - defensive guard path
        findings.append(_finding("grouped_constructor_error", type(exc).__name__, str(exc)))

    flat_constructor_ok = flat_context is not None
    grouped_constructor_ok = grouped_context is not None
    legacy_access_ok = True
    dataclasses_replace_ok = True

    if flat_context is not None:
        legacy_access_ok &= _check_context_access(
            flat_context,
            group_classes,
            group_field_names,
            flat_kwargs,
            "flat",
            findings,
        )
    if grouped_context is not None:
        legacy_access_ok &= _check_context_access(
            grouped_context,
            group_classes,
            group_field_names,
            flat_kwargs,
            "grouped",
            findings,
        )
        dataclasses_replace_ok = _check_dataclasses_replace(grouped_context, findings)
    else:
        dataclasses_replace_ok = False

    return {
        "ok": not findings,
        "schema_version": SCHEMA_VERSION,
        "module": module_name,
        "top_level_field_count": len(top_level_field_names),
        "top_level_field_names": top_level_field_names,
        "group_field_counts": {group_name: len(names) for group_name, names in group_field_names.items()},
        "group_field_names": group_field_names,
        "duplicate_field_names": duplicate_field_names,
        "flat_constructor_ok": flat_constructor_ok,
        "grouped_constructor_ok": grouped_constructor_ok,
        "legacy_access_ok": legacy_access_ok,
        "dataclasses_replace_ok": dataclasses_replace_ok,
        "findings": findings,
    }


def _check_context_access(
    context: Any,
    group_classes: dict[str, Any],
    group_field_names: dict[str, list[str]],
    flat_kwargs: dict[str, Any],
    label: str,
    findings: list[dict[str, str]],
) -> bool:
    ok = True
    for group_name, group_class in group_classes.items():
        group = getattr(context, group_name)
        if not isinstance(group, group_class):
            findings.append(
                _finding(
                    f"{label}_group_type",
                    f"{group_name}:{type(group).__name__}",
                    "context group should preserve its dedicated dataclass type",
                )
            )
            ok = False
            continue
        for field_name in group_field_names[group_name]:
            expected = flat_kwargs[field_name]
            actual = getattr(group, field_name)
            if actual is not expected:
                findings.append(
                    _finding(
                        f"{label}_group_field",
                        f"{group_name}.{field_name}",
                        "grouped context field should preserve the original dependency value",
                    )
                )
                ok = False

    for field_name, expected in flat_kwargs.items():
        actual = getattr(context, field_name)
        if actual is not expected:
            findings.append(
                _finding(
                    f"{label}_legacy_field",
                    field_name,
                    "legacy flat attribute access should still resolve through __getattr__",
                )
            )
            ok = False

    return ok


def _check_dataclasses_replace(context: Any, findings: list[dict[str, str]]) -> bool:
    replacements = {
        "route_for": object(),
        "jobs": object(),
        "validate_run_payload": object(),
        "submit_lock": object(),
    }
    try:
        updated = dataclasses.replace(context, **replacements)
    except Exception as exc:
        findings.append(_finding("dataclasses_replace_error", type(exc).__name__, str(exc)))
        return False

    ok = True
    for field_name, expected in replacements.items():
        actual = getattr(updated, field_name)
        if actual is not expected:
            findings.append(
                _finding(
                    "dataclasses_replace_field",
                    field_name,
                    "dataclasses.replace should allow legacy flat dependency overrides",
                )
            )
            ok = False
    return ok


def _finding(code: str, value: str, message: str) -> dict[str, str]:
    return {"code": code, "value": value, "message": message}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check WebHandlerDispatchContext grouping contract.")
    parser.add_argument("--module", default=DEFAULT_MODULE, help="Python module that exports the dispatch context")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = parser.parse_args()

    result = check_web_handler_dispatch_context(args.module)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        state = "PASS" if result["ok"] else "FAIL"
        print(f"web handler dispatch context check {state}: {result['module']}")
        for finding in result["findings"]:
            print(f"- {finding['code']}: {finding['value']} ({finding['message']})")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
