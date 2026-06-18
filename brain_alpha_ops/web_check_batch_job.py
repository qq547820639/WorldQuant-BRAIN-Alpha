"""Backward-compatible import for the batch check job service."""

from __future__ import annotations

from brain_alpha_ops.web_check_availability import run_check_batch_job_service

__all__ = ["run_check_batch_job_service"]
