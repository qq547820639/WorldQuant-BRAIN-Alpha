from __future__ import annotations

import os
from pathlib import Path
import subprocess


def test_runtime_generated_data_paths_are_ignored():
    gitignore = (Path(__file__).resolve().parents[1] / ".gitignore").read_text(encoding="utf-8")

    for pattern in (
        "data/*.jsonl",
        "data/*.sqlite",
        "data/run_history/",
        "data/knowledge/",
        "data/api_cache/",
        "data/_codex_bench*/",
        "data/checkpoints/",
        "data/*.log",
        "data/e2e_screenshots/",
    ):
        assert pattern in gitignore


def test_runtime_generated_data_examples_are_git_ignored():
    root = Path(__file__).resolve().parents[1]
    examples = [
        "data/example.jsonl",
        "data/example.sqlite",
        "data/run_history/run_example.json",
        "data/knowledge/failures/example.json",
        "data/api_cache/example.json",
        "data/_codex_bench/example.jsonl",
        "data/checkpoints/run_example.checkpoint.json",
        "data/e2e_screenshots/example.png",
        "data/example.log",
    ]

    # Create dummy files so git check-ignore can evaluate them
    created_files = []
    for example in examples:
        file_path = root / example
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if not file_path.exists():
            file_path.write_text("", encoding="utf-8")
            created_files.append(file_path)

    try:
        proc = subprocess.run(
            ["git", "check-ignore", "--no-index"] + examples,
            cwd=root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )

        assert proc.returncode == 0
        actual = set(
            line.strip().replace("\\r", "")
            for line in proc.stdout.splitlines()
        )
        assert actual == set(examples)
    finally:
        # Clean up created files
        for file_path in created_files:
            if file_path.exists():
                file_path.unlink()
