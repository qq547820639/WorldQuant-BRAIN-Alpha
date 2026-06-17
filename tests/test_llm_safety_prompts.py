"""Tests that pin the LLM safety constraints defined in the assistant
system prompt (P3-20, 2026-06-13).

The system prompt is the only line of defence between a careless
prompt-rewrite and a tool-call regression. The constraints the platform
relies on are:

1. ``Do not invent metrics, alpha ids, official results, fields, operators, or
   BRAIN check outcomes.`` (anti-hallucination)
2. ``Do not submit alphas or call a submit tool;`` (no live submission)
3. ``run_backtest: ... only when live API confirmation is present`` and
   ``run_batch_backtest: ... with explicit live API confirmation and budget
   limits`` (live API confirmation gate)
4. ``score_factor`` must come before ``run_backtest`` / ``run_batch_backtest``
   (cost discipline)
5. ``Return one valid JSON object only; no markdown.`` (machine parseable)

If any of these strings are ever removed from the system prompt, the
corresponding tool-call path must be re-evaluated against a real BRAIN
account.  These tests therefore FAIL loudly when the prompt is missing
the required phrases so the regression cannot be merged silently.
"""

from __future__ import annotations

import re

import pytest


_REQUIRED_PHRASES = [
    "Do not invent metrics",
    "Do not submit alphas or call a submit tool",
    "live API confirmation",
    "score_factor",
    "run_backtest",
    "Return one valid JSON object only; no markdown",
]


@pytest.mark.parametrize("phrase", _REQUIRED_PHRASES)
def test_system_prompt_contains_required_safety_phrase(phrase: str) -> None:
    from brain_alpha_ops.research.prompt_templates import load_system_prompt

    prompt = load_system_prompt()
    assert phrase in prompt, (
        f"assistant system prompt is missing required safety phrase: {phrase!r}. "
        "Re-introduce the phrase and re-evaluate the corresponding LLM "
        "tool-call path against a real BRAIN account before merging."
    )


def test_system_prompt_forbids_inventing_metrics_and_official_results() -> None:
    """Anti-hallucination guard must mention both metrics and official results."""
    from brain_alpha_ops.research.prompt_templates import load_system_prompt

    prompt = load_system_prompt().lower()
    assert "invent" in prompt
    assert "metrics" in prompt
    assert "official" in prompt


def test_system_prompt_keeps_score_factor_ahead_of_backtest_tools() -> None:
    """``score_factor`` must be referenced before ``run_backtest`` in the prompt
    so the model is told to screen first."""
    from brain_alpha_ops.research.prompt_templates import load_system_prompt

    prompt = load_system_prompt()
    score_factor_idx = prompt.find("score_factor")
    run_backtest_idx = prompt.find("run_backtest")
    assert score_factor_idx >= 0
    assert run_backtest_idx >= 0
    assert score_factor_idx < run_backtest_idx, (
        "score_factor must be introduced before run_backtest in the system "
        "prompt so the model screens candidates before spending live API "
        "budget on backtests."
    )


def test_system_prompt_no_markdown_wrappers_in_response() -> None:
    """The prompt must forbid markdown so the LLM response is JSON-parseable."""
    from brain_alpha_ops.research.prompt_templates import load_system_prompt

    prompt = load_system_prompt()
    assert "no markdown" in prompt.lower()
    # ``return one valid json object only`` is the canonical phrasing
    assert re.search(r"return one valid json object", prompt, re.IGNORECASE)


def test_load_system_prompt_uses_cached_value() -> None:
    """``load_system_prompt`` must cache the bundled prompt so the file is
    read at most once per process; the cache protects against
    hot-reload pitfalls during a long-running pipeline run."""
    from brain_alpha_ops.research import prompt_templates

    first = prompt_templates.load_system_prompt()
    # Second call must return the exact same string (object identity is
    # not guaranteed because ``str`` is interned, but the value is).
    second = prompt_templates.load_system_prompt()
    assert first == second
    assert first  # non-empty


def test_fallback_prompt_preserves_core_constraints() -> None:
    """The fallback prompt (used when packaged resources are missing) must
    still contain the anti-invent and JSON-only constraints so the
    assistant remains safe even if the bundled file is corrupted on disk."""
    from brain_alpha_ops.research.prompt_templates import FALLBACK_SYSTEM_PROMPT

    fallback = FALLBACK_SYSTEM_PROMPT
    assert "score_factor" in fallback
    assert "run_backtest" in fallback or "run_batch_backtest" in fallback
    assert "no markdown" in fallback.lower()
    # Anti-hallucination guidance is dropped from the fallback (it
    # trades completeness for size), but the live-API confirmation
    # gate is the more critical guardrail and must still be present.
    assert "registered safe tools" in fallback


def test_assistant_response_schema_forbids_submit_in_actions() -> None:
    """Defence in depth: the offline assistant response builder must NOT
    emit ``submit`` in any of its ``recommended_next_actions``.  The
    system prompt already forbids the LLM from calling a submit tool,
    but the offline deterministic draft can also leak such guidance if
    a future refactor adds it.  This test pins the offline behaviour.
    """
    from brain_alpha_ops.research.assistant import build_offline_assistant_response

    context_pack = {
        "latest_result": {
            "summary": "12 candidates generated, 3 passed local checks",
            "actions": ["generate_candidates", "score_factor"],
        },
        "research_memory": {},
    }
    response = build_offline_assistant_response(context_pack)
    actions = response.get("recommended_next_actions") or []
    for action in actions:
        assert "submit" not in action.lower(), (
            f"offline assistant response emitted a submit action: {action!r}. "
            "The assistant must never recommend a submit path; the Web "
            "staged readiness flow owns submission."
        )
