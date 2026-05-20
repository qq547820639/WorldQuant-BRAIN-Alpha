"""Static dependency policy checks for local quality gates.

The check is intentionally offline: it catches risky dependency shapes that do
not require a vulnerability database, while pip-audit remains available as the
optional online advisory check.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PYPROJECT = ROOT / "pyproject.toml"


def check_dependency_policy(pyproject_path: str | Path = DEFAULT_PYPROJECT) -> dict[str, Any]:
    path = Path(pyproject_path)
    payload = _load_pyproject(path)
    project = payload.get("project") if isinstance(payload.get("project"), dict) else {}
    entries: list[tuple[str, str, str]] = []
    for dependency in project.get("dependencies") or []:
        entries.append(("project.dependencies", str(dependency), "runtime"))
    optional = project.get("optional-dependencies") if isinstance(project.get("optional-dependencies"), dict) else {}
    for group, values in optional.items():
        for dependency in values or []:
            entries.append((f"project.optional-dependencies.{group}", str(dependency), "optional"))

    findings: list[dict[str, str]] = []
    for section, dependency, kind in entries:
        lowered = dependency.lower()
        if " @ " in dependency or "://" in dependency or lowered.startswith(("file:", "git+", "http:", "https:")):
            findings.append(_finding(section, dependency, "direct_reference", "Use package index names with version bounds, not direct URL/path references."))
        if not _has_lower_bound(dependency):
            findings.append(_finding(section, dependency, "missing_lower_bound", "Add a minimum version bound."))
        if kind == "runtime" and not _has_upper_bound(dependency):
            findings.append(_finding(section, dependency, "missing_runtime_upper_bound", "Add an upper major-version bound for runtime dependencies."))
        if kind == "optional" and _looks_tool_dependency(dependency) and not _has_upper_bound(dependency):
            findings.append(_finding(section, dependency, "missing_tool_upper_bound", "Add an upper major-version bound for tooling dependencies."))

    return {
        "ok": not findings,
        "schema_version": "dependency_policy.v1",
        "path": str(path),
        "checked": len(entries),
        "findings": findings,
    }


def _load_pyproject(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import tomllib
    except ModuleNotFoundError:
        return _minimal_pyproject_parse(text)
    return tomllib.loads(text)


def _minimal_pyproject_parse(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {"project": {"dependencies": [], "optional-dependencies": {}}}
    section = ""
    active_key = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line.strip("[]")
            active_key = ""
            continue
        if section == "project" and line.startswith("dependencies"):
            active_key = "dependencies"
            continue
        if section == "project.optional-dependencies" and line.endswith("["):
            active_key = line.split("=", 1)[0].strip()
            result["project"]["optional-dependencies"].setdefault(active_key, [])
            continue
        if active_key and line.startswith("]"):
            active_key = ""
            continue
        if active_key and line.startswith('"'):
            value = line.strip().rstrip(",").strip('"')
            if section == "project":
                result["project"]["dependencies"].append(value)
            elif section == "project.optional-dependencies":
                result["project"]["optional-dependencies"].setdefault(active_key, []).append(value)
    return result


def _has_lower_bound(dependency: str) -> bool:
    return bool(re.search(r">=\s*[0-9]", dependency))


def _has_upper_bound(dependency: str) -> bool:
    return bool(re.search(r"(?<![<>=!])<\s*[0-9]", dependency))


def _looks_tool_dependency(dependency: str) -> bool:
    name = re.split(r"[<>=!~;\[]", dependency, maxsplit=1)[0].strip().lower()
    return name in {"mypy", "pip-audit", "pytest", "pytest-cov", "ruff"}


def _finding(section: str, dependency: str, code: str, message: str) -> dict[str, str]:
    return {"section": section, "dependency": dependency, "code": code, "message": message}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check pyproject dependency policy.")
    parser.add_argument("--pyproject", default=str(DEFAULT_PYPROJECT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = check_dependency_policy(args.pyproject)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["ok"]:
            print(f"Dependency policy passed: {result['checked']} entries checked.")
        else:
            for finding in result["findings"]:
                print(f"[{finding['code']}] {finding['section']} {finding['dependency']}: {finding['message']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
