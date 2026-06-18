"""Domain API (v4.0) — clean bounded-context access."""
from brain_alpha_ops.domains.backtest import LocalBacktestEngine
from brain_alpha_ops.domains.generation import CandidateGenerator
from brain_alpha_ops.domains.scoring import AlphaCheckRegistry, build_scorecard
from brain_alpha_ops.domains.simulation import OfficialValidationService
