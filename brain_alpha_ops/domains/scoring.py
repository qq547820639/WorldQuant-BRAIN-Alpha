"""Scoring domain — scorecards, quality gates, anti-overfit, convergence (v4.0)."""
from brain_alpha_ops.research.alpha_checks import AlphaCheckRegistry
from brain_alpha_ops.research.anti_overfit import AntiOverfitService
from brain_alpha_ops.research.convergence import ConvergenceTracker
from brain_alpha_ops.research.scoring import build_scorecard, evaluate_quality_gate
