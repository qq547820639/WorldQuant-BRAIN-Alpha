#!/usr/bin/env python3
"""Validate cached official BRAIN context JSON files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


DEFAULT_DATA_DIR = Path("data")


def validate_json_file(
    path: Path,
    *,
    expected_count: int | None = None,
    required_fields: list[str] | None = None,
    nested_fields: dict[str, list[str]] | None = None,
) -> tuple[bool, str]:
    print(f"\n{'=' * 60}")
    print(f"Validating {path}")
    print(f"{'=' * 60}")

    if not path.exists():
        return False, f"file does not exist: {path}"

    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, f"invalid JSON: {exc}"
    except OSError as exc:
        return False, f"could not read file: {exc}"

    if not isinstance(data, list):
        return False, f"expected a list, got {type(data).__name__}"

    print(f"Rows: {len(data)}; size: {path.stat().st_size / 1024:.2f} KB")
    if expected_count is not None and len(data) != expected_count:
        return False, f"expected {expected_count} rows, got {len(data)}"

    if data and required_fields:
        first = data[0]
        if not isinstance(first, dict):
            return False, f"first item is not an object: {type(first).__name__}"
        missing = [field for field in required_fields if field not in first]
        if missing:
            return False, f"missing required fields: {missing}"

    if data and nested_fields:
        first = data[0]
        if not isinstance(first, dict):
            return False, f"first item is not an object: {type(first).__name__}"
        for parent, children in nested_fields.items():
            value = first.get(parent)
            if not isinstance(value, dict):
                return False, f"{parent} is not an object"
            missing = [field for field in children if field not in value]
            if missing:
                return False, f"{parent} missing nested fields: {missing}"

    return True, "passed"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate official context cache files")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--strict-counts", action="store_true", help="require historical row counts")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    validations = [
        {
            "path": data_dir / "official_fields.json",
            "expected_count": 7642 if args.strict_counts else None,
            "required_fields": ["id", "description", "dataset", "category", "region", "delay", "universe", "type"],
            "nested_fields": {"dataset": ["id", "name"], "category": ["id", "name"]},
        },
        {
            "path": data_dir / "official_operators.json",
            "expected_count": 66 if args.strict_counts else None,
            "required_fields": ["name", "category", "scope", "definition", "description"],
        },
        {
            "path": data_dir / "official_datasets.json",
            "expected_count": 16 if args.strict_counts else None,
            "required_fields": ["id", "name", "field_count"],
        },
    ]

    all_passed = True
    for spec in validations:
        ok, message = validate_json_file(**spec)
        print(f"{'PASS' if ok else 'FAIL'}: {message}")
        all_passed = all_passed and ok

    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
