"""Git invocation helpers for tracked-data inventory.

Split from the former ``scripts/check_tracked_data_inventory.py`` monolith
(Task A7 of deep-optimization-phase12). Wraps the ``git ls-files`` and
``git diff`` calls used to enumerate tracked files under ``data/`` and to
compute the locally modified subset, plus the ``git grep`` helper that
finds references to runtime-generated data files outside the excluded
``data/`` and ``tests/`` trees.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _tracked_data_files(root: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files", "data"],
        cwd=str(root),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _changed_tracked_data_files(root: Path) -> list[str]:
    changed: set[str] = set()
    for args in (
        ["git", "diff", "--name-only", "--", "data"],
        ["git", "diff", "--cached", "--name-only", "--", "data"],
    ):
        proc = subprocess.run(
            args,
            cwd=str(root),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        if proc.returncode != 0:
            continue
        for line in proc.stdout.splitlines():
            rel_path = line.strip().replace("\\", "/")
            if rel_path:
                changed.add(rel_path)
    return sorted(changed)


def _runtime_generated_references(root: Path, runtime_generated: list[str]) -> dict[str, list[str]]:
    references: dict[str, list[str]] = {}
    for rel_path in runtime_generated:
        proc = subprocess.run(
            ["git", "grep", "-n", "-F", "--", rel_path],
            cwd=str(root),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        if proc.returncode not in (0, 1):
            continue
        matches: set[str] = set()
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            ref_path = line.split(":", 1)[0].strip().replace("\\", "/")
            if _is_reference_excluded(ref_path):
                continue
            matches.add(line.strip())
        if matches:
            references[rel_path] = sorted(matches)
    return references


def _is_reference_excluded(path: str) -> bool:
    from ._constants import REFERENCE_EXCLUDED_PATHS, REFERENCE_EXCLUDED_PREFIXES

    normalized = path.replace("\\", "/")
    if normalized in REFERENCE_EXCLUDED_PATHS:
        return True
    return normalized.startswith(REFERENCE_EXCLUDED_PREFIXES)
