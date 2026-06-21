"""Minimal i18n framework for BRAIN Alpha Ops (Phase 4.1).

Usage:
    from brain_alpha_ops.i18n import t

    msg = t("submission.blocked.missing_id")
    # → "缺少官方 Alpha ID，请先完成官方回测。"

All user-facing Chinese strings SHOULD route through this module.
English-fallback keys are optionally stored in ``messages.py``.
"""
from __future__ import annotations

from brain_alpha_ops.i18n.messages import _MESSAGES

_DEFAULT_LANG = "zh"


def t(key: str, *, lang: str = _DEFAULT_LANG, default: str = "", **kwargs) -> str:
    """Look up a localised message by stable key.

    Args:
        key: Dot-delimited message id (e.g. "submission.blocked.missing_id").
        lang: Language code; defaults to "zh".
        default: Fallback when no translation is found.
        **kwargs: Format variables (passed to ``str.format``).

    Returns:
        The translated string, or *default* if the key is not found.
    """
    entry = _MESSAGES.get(key)
    if entry is None:
        return default or key
    text = entry.get(lang) or entry.get(_DEFAULT_LANG) or default or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return text


# Convenience: t() is also available as _()
_ = t
