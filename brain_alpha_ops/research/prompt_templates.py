"""Packaged prompt-template loading for LLM workflows."""

from __future__ import annotations

from importlib import resources


SYSTEM_PROMPT_TEMPLATE = "assistant_system_prompt.txt"
FALLBACK_SYSTEM_PROMPT = (
    "You are a quantitative factor research agent for WorldQuant BRAIN FASTEXPR. "
    "Use only the supplied local context and registered safe tools. "
    "Use score_factor before run_backtest or run_batch_backtest. "
    "Return one valid JSON object only; no markdown."
)

_SYSTEM_PROMPT_CACHE = ""


def load_system_prompt(template_name: str = SYSTEM_PROMPT_TEMPLATE) -> str:
    """Load the assistant system prompt from packaged prompt templates."""
    global _SYSTEM_PROMPT_CACHE
    if template_name == SYSTEM_PROMPT_TEMPLATE and _SYSTEM_PROMPT_CACHE:
        return _SYSTEM_PROMPT_CACHE
    try:
        prompt = resources.files("brain_alpha_ops.research.prompts").joinpath(template_name).read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        prompt = FALLBACK_SYSTEM_PROMPT
    prompt = str(prompt or "").strip() or FALLBACK_SYSTEM_PROMPT
    if template_name == SYSTEM_PROMPT_TEMPLATE:
        _SYSTEM_PROMPT_CACHE = prompt
    return prompt
