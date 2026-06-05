from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_launch_monitor():
    path = Path(__file__).resolve().parents[1] / "_launch_monitor.py"
    spec = importlib.util.spec_from_file_location("_launch_monitor_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_launch_monitor_sanitized_child_env_removes_brain_credentials():
    module = _load_launch_monitor()

    env = module.sanitized_child_env({
        "PATH": "/usr/bin",
        "PYTHONHOME": "/tmp/fake-python-home",
        "PYTHONPATH": "/tmp/malicious",
        "BRAIN_USERNAME": "user@example.com",
        "BRAIN_PASSWORD": "secret",
        "BRAIN_TOKEN": "token",
        "BRAIN_ALPHA_OPS_ADMIN_TOKEN": "admin",
        "UNRELATED_SECRET": "not-allowlisted",
    })

    assert env == {"PATH": "/usr/bin"}


def test_launch_monitor_main_rejects_arguments(capsys):
    module = _load_launch_monitor()

    assert module.main(["--unexpected"]) == 2
    assert "unsupported arguments" in capsys.readouterr().out
