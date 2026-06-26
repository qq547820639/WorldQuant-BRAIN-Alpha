"""Per-process LLM call quota tracker (P3-4)."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

# P3-4: per-instance token quota.  A pipeline run that loops over hundreds
# of LLM reviews can otherwise burn through the OpenAI quota in a single
# cycle.  The cap is conservative; bump via env if your account is
# provisioned for higher throughput.
LLM_CALL_TOKEN_BUDGET_PER_RUN: int = 200_000
LLM_CALL_MIN_INTERVAL_SECONDS: float = 0.5  # basic rate-limit between calls


class LLMCallLedger:
    """Thread-safe per-process quota tracker for LLM calls (P3-4).

    Tracks cumulative prompt/completion tokens and enforces a soft cap.
    Failures are also counted; ``consecutive_failures`` triggers an
    exponential cool-down (see ``record_failure``).
    """

    def __init__(
        self,
        *,
        token_budget: int = LLM_CALL_TOKEN_BUDGET_PER_RUN,
        min_interval_seconds: float = LLM_CALL_MIN_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._token_budget = max(0, int(token_budget))
        self._min_interval = max(0.0, float(min_interval_seconds))
        self._clock = clock
        self._tokens_used: int = 0
        self._calls: int = 0
        self._failures: int = 0
        self._consecutive_failures: int = 0
        self._last_call_at: float = 0.0
        self._lock = threading.Lock()

    def budget_exhausted(self) -> bool:
        with self._lock:
            return self._tokens_used >= self._token_budget

    def record(
        self,
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int | None = None,
    ) -> None:
        tokens = int(total_tokens) if total_tokens is not None else int(prompt_tokens) + int(completion_tokens)
        with self._lock:
            self._tokens_used += max(0, tokens)
            self._calls += 1
            self._consecutive_failures = 0
            self._last_call_at = self._clock()

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            self._consecutive_failures += 1

    def wait_for_quota(self) -> None:
        """Sleep until the next call is allowed. Returns immediately if not.

        Implements basic per-call spacing (``min_interval_seconds``) and
        exponential back-off after consecutive failures.
        """
        with self._lock:
            now = self._clock()
            spacing = self._min_interval
            if self._consecutive_failures > 0:
                spacing *= 2 ** min(self._consecutive_failures, 5)
            wait = max(0.0, spacing - (now - self._last_call_at))
        if wait > 0:
            time.sleep(wait)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "tokens_used": self._tokens_used,
                "token_budget": self._token_budget,
                "calls": self._calls,
                "failures": self._failures,
                "consecutive_failures": self._consecutive_failures,
            }
