#!/usr/bin/env python3
"""Generate a Software Bill of Materials (SBOM) from pyproject.toml and package.json.

Reads Python dependencies from pyproject.toml and Node.js dependencies from
package.json, then outputs a structured JSON SBOM file.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PYPROJECT = ROOT / "pyproject.toml"
DEFAULT_PACKAGE_JSON = ROOT / "brain_alpha_ops" / "web" / "react_app" / "package.json"


def generate_sbom(
    pyproject_path: str | Path = DEFAULT_PYPROJECT,
    package_json_path: str | Path = DEFAULT_PACKAGE_JSON,
) -> dict[str, Any]:
    pyproject = _load_pyproject(pyproject_path)
    package = _load_package_json(package_json_path)

    python_deps = _extract_python_deps(pyproject)
    node_deps = _extract_node_deps(package)

    project = pyproject.get("project", {})
    return {
        "sbom_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": {
            "name": project.get("name", "unknown"),
            "version": project.get("version", "unknown"),
        },
        "python_dependencies": python_deps,
        "node_dependencies": node_deps,
    }


def _load_pyproject(path: str | Path) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    try:
        import tomllib  # type: ignore[import-untyped]
        return tomllib.loads(text)
    except (ModuleNotFoundError, AttributeError):
        return _parse_toml_simple(text)


def _parse_toml_simple(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {"project": {"name": "", "version": "", "dependencies": [], "optional-dependencies": {}}}
    active_section: str | None = None
    active_key: str | None = None
    bracket_depth = 0
    array_buffer: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("[project.optional-dependencies"):
            active_section = "project.optional-dependencies"
            active_key = None
            continue
        if stripped.startswith("[project]"):
            active_section = "project"
            active_key = None
            continue
        if stripped.startswith("[") and not stripped.startswith("[project"):
            active_section = None
            active_key = None
            continue

        # continuation of a multi-line array (check BEFORE '=' to avoid matching '>=' inside values)
        if bracket_depth > 0:
            bracket_depth += stripped.count("[") - stripped.count("]")
            array_buffer.extend(re.findall(r'"((?:\\.|[^"\\])*)"', stripped))
            if bracket_depth == 0:
                decoded = [s.replace('\\"', '"') for s in array_buffer]
                if active_section == "project" and active_key == "dependencies":
                    result["project"]["dependencies"] = decoded
                elif active_section == "project.optional-dependencies" and active_key:
                    result["project"]["optional-dependencies"][active_key] = decoded
                array_buffer = []
                active_key = None
        elif "=" in stripped:
            key, val = stripped.split("=", 1)
            key = key.strip()
            val = val.strip()

            if active_section == "project":
                active_key = key
                if key == "name":
                    result["project"]["name"] = _extract_toml_string(val)
                    active_key = None
                elif key == "version":
                    result["project"]["version"] = _extract_toml_string(val)
                    active_key = None
                elif key == "dependencies":
                    if val.startswith("["):
                        bracket_depth = val.count("[") - val.count("]")
                        array_buffer = re.findall(r'"((?:\\.|[^"\\])*)"', val)
                        if bracket_depth == 0:
                            result["project"]["dependencies"] = [s.replace('\\"', '"') for s in array_buffer]
                            array_buffer = []
                            active_key = None
                    else:
                        result["project"]["dependencies"] = [_extract_toml_string(val)] if val else []
                        active_key = None
            elif active_section == "project.optional-dependencies":
                active_key = key
                if val.startswith("["):
                    bracket_depth = val.count("[") - val.count("]")
                    array_buffer = re.findall(r'"((?:\\.|[^"\\])*)"', val)
                    if bracket_depth == 0:
                        result["project"]["optional-dependencies"][active_key] = [s.replace('\\"', '"') for s in array_buffer]
                        array_buffer = []
                        active_key = None
                else:
                    result["project"]["optional-dependencies"][active_key] = [_extract_toml_string(val)] if val else []
                    active_key = None

    return result


def _extract_toml_string(val: str) -> str:
    match = re.match(r'^"((?:\\.|[^"\\])*)"', val)
    return match.group(1).replace('\\"', '"') if match else val


def _load_package_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _extract_python_deps(pyproject: dict[str, Any]) -> list[dict[str, str]]:
    deps: list[dict[str, str]] = []
    project = pyproject.get("project", {})
    for dep in project.get("dependencies") or []:
        name, version_spec = _split_dep(str(dep))
        deps.append({"name": name, "version_spec": version_spec, "category": "core"})
    for group, values in (project.get("optional-dependencies") or {}).items():
        for dep in values or []:
            name, version_spec = _split_dep(str(dep))
            deps.append({"name": name, "version_spec": version_spec, "category": f"optional.{group}"})
    return deps


def _extract_node_deps(package: dict[str, Any]) -> list[dict[str, str]]:
    deps: list[dict[str, str]] = []
    for section in ("dependencies", "devDependencies"):
        for name, version in (package.get(section) or {}).items():
            deps.append({"name": name, "version_spec": str(version), "category": section})
    return deps


def _split_dep(dep: str) -> tuple[str, str]:
    match = re.match(r'^([A-Za-z0-9_\-.\[\]]+)(.*)', dep)
    if match:
        return match.group(1), match.group(2).strip()
    return dep, ""


def _sbom_to_csv(sbom: dict[str, Any]) -> str:
    lines = ["type,name,version_spec,category"]
    for dep in sbom.get("python_dependencies", []):
        lines.append(f"python,{dep['name']},{dep['version_spec']},{dep['category']}")
    for dep in sbom.get("node_dependencies", []):
        lines.append(f"node,{dep['name']},{dep['version_spec']},{dep['category']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate SBOM from pyproject.toml and package.json.")
    parser.add_argument("--pyproject", default=str(DEFAULT_PYPROJECT), help="Path to pyproject.toml")
    parser.add_argument("--package-json", default=str(DEFAULT_PACKAGE_JSON), help="Path to package.json")
    parser.add_argument("--output", "-o", default="sbom.json", help="Output file path (default: sbom.json)")
    parser.add_argument("--format", choices=["json", "csv"], default="json", help="Output format")
    args = parser.parse_args(argv)

    sbom = generate_sbom(args.pyproject, args.package_json)

    output_path = Path(args.output)
    if args.format == "csv":
        output_path.write_text(_sbom_to_csv(sbom), encoding="utf-8")
    else:
        output_path.write_text(json.dumps(sbom, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    total = len(sbom["python_dependencies"]) + len(sbom["node_dependencies"])
    print(f"SBOM generated: {output_path} ({total} dependencies)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
