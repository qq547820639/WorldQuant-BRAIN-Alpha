from importlib import util
from pathlib import Path


def test_user_facing_cli_modules_are_retired():
    root = Path(__file__).resolve().parents[1]

    retired_paths = [
        "brain_alpha_ops/cli.py",
        "brain_alpha_ops/cli_parser.py",
        "brain_alpha_ops/cli_handlers.py",
        "brain_alpha_ops/ux/guided_cli.py",
        "run_pipeline.py",
    ]
    for relative in retired_paths:
        assert not (root / relative).exists()

    assert util.find_spec("brain_alpha_ops.cli") is None


def test_no_installable_console_script_surface_is_declared():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "[project.scripts]" not in pyproject
    assert "console_scripts" not in pyproject
