"""Shared lazy-accessor helpers for web facade bindings."""

from __future__ import annotations


def _web():
    from brain_alpha_ops import web

    return web


def _app_context():
    return _web()._app_context()


def _runtime_facade():
    return _web()._runtime_facade


def _snapshot_facade():
    from brain_alpha_ops import web

    return web._snapshot_facade()
