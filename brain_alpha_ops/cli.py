"""Command line entry point for BRAIN Alpha Ops."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from brain_alpha_ops.cli_handlers import (
    COMMAND_HANDLERS,
    _load_json_argument,
    _print_cli_error,
    build_assistant_guidance_audit,
    run_command,
)
from brain_alpha_ops.cli_parser import build_parser
from brain_alpha_ops.config import ConfigValidationError
from brain_alpha_ops.runner import run_pipeline_from_config


logger = logging.getLogger(__name__)

__all__ = [
    "COMMAND_HANDLERS",
    "_load_json_argument",
    "_main",
    "build_assistant_guidance_audit",
    "build_parser",
    "main",
    "run_pipeline_from_config",
]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _main(args, parser)
    except ConfigValidationError as exc:
        _print_cli_error("CONFIG_VALIDATION_ERROR", exc, config_path=getattr(args, "config", ""))
        return 1
    except json.JSONDecodeError as exc:
        _print_cli_error("CONFIG_JSON_ERROR", exc, config_path=getattr(args, "config", ""))
        return 1
    except Exception as exc:
        # Catch-all: prevent raw traceback from leaking to CLI output.
        logger.warning("brain-alpha-ops CLI command failed unexpectedly", exc_info=True)
        _print_cli_error("UNEXPECTED_ERROR", exc)
        return 1


def _main(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    return run_command(args, parser)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
