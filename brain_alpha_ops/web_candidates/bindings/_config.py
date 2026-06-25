"""Web run/config payload bindings."""

from __future__ import annotations

from ._helpers import _web


def load_run_config_provider():
    web = _web()
    return web._load_run_config


def runtime_project_root_provider():
    web = _web()
    return web._runtime_project_root


def run_config_from_payload(payload):
    web = _web()
    return web._run_config_from_payload(payload, loader=web._load_run_config_provider())


def config_from_payload(payload):
    web = _web()
    return web._config_from_payload(payload, loader=web._load_run_config_provider())


def save_run_config_payload(payload):
    web = _web()
    return web._save_run_config_payload(payload, loader=web._load_run_config_provider())
