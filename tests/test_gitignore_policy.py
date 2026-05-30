from __future__ import annotations

from pathlib import Path
import subprocess


def test_runtime_generated_data_paths_are_ignored():
    gitignore = (Path(__file__).resolve().parents[1] / ".gitignore").read_text(encoding="utf-8")

    for pattern in (
        "data/*.jsonl",
        "data/*.sqlite",
        "data/jobs_production.json",
        "data/jobs_sync.json",
        "data/jobs_check.json",
        "data/jobs_async.json",
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
        "data/jobs_production.json",
        "data/jobs_sync.json",
        "data/jobs_check.json",
        "data/jobs_async.json",
        "data/run_history/run_example.json",
        "data/knowledge/failures/example.json",
        "data/api_cache/example.json",
        "data/_codex_bench/example.jsonl",
        "data/checkpoints/run_example.checkpoint.json",
        "data/e2e_screenshots/example.png",
        "data/example.log",
    ]

    proc = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"],
        cwd=root,
        input="\n".join(examples) + "\n",
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )

    assert proc.returncode == 0
    assert set(proc.stdout.splitlines()) == set(examples)
