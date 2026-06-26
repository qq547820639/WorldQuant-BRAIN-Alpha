"""Config payload functions."""
from __future__ import annotations

import os
from typing import Any

from brain_alpha_ops.config import (
    OpsConfig,
    RunConfig,
    load_run_config,
    write_run_config,
)
from brain_alpha_ops.web.config.web_config._constants import (
    RunConfigLoader,
    RunConfigWriter,
)
from brain_alpha_ops.web.config.web_config._run_config import run_config_from_payload


def config_from_payload(payload: dict, *, loader: RunConfigLoader = load_run_config) -> OpsConfig:
    return run_config_from_payload(payload, loader=loader).ops


def public_run_config_dict(config: RunConfig) -> dict[str, Any]:
    data = config.to_dict()
    credentials = data.get("credentials", {})
    data["credentials"] = {
        "username": "",
        "password": "",
        "token": "",
        "username_env": credentials.get("username_env", "BRAIN_USERNAME"),
        "password_env": credentials.get("password_env", "BRAIN_PASSWORD"),
        "token_env": credentials.get("token_env", "BRAIN_TOKEN"),
        "managed_credentials_available": managed_credentials_available(credentials),
    }
    return data


def managed_credentials_available(credentials: dict[str, Any]) -> bool:
    """Return only whether runtime credentials exist, never their values."""
    token_env = str(credentials.get("token_env") or "BRAIN_TOKEN")
    username_env = str(credentials.get("username_env") or "BRAIN_USERNAME")
    password_env = str(credentials.get("password_env") or "BRAIN_PASSWORD")
    token = str(credentials.get("token") or os.getenv(token_env, ""))
    username = str(credentials.get("username") or os.getenv(username_env, ""))
    password = str(credentials.get("password") or os.getenv(password_env, ""))
    return bool(token) or bool(username and password)


def save_run_config_payload(
    payload: dict,
    *,
    loader: RunConfigLoader = load_run_config,
    writer: RunConfigWriter = write_run_config,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")
    run_config = run_config_from_payload(payload, loader=loader)
    run_config.auto_submit = False
    run_config.credentials.username = ""
    run_config.credentials.password = ""
    run_config.credentials.token = ""
    saved_path = writer(run_config)
    return {
        "ok": True,
        "config": public_run_config_dict(run_config),
        "path": str(saved_path),
    }


from brain_alpha_ops.web.dispatch.web_post_handlers import connection_test_post_payload  # noqa: F401
