"""Adaptive strategy switching helpers for AlphaResearchPipeline.

Migrated from PipelineStrategyMixin to standalone class
using composition instead of inheritance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from brain_alpha_ops.models import Candidate

from .pipeline_helpers import rank_candidates
from .production_context import eligible_strategy_profiles
from .strategy_switch import StrategySwitchService

if TYPE_CHECKING:
    from .pipeline import AlphaResearchPipeline


class StrategyService:
    """Standalone strategy service using composition.

    Takes a pipeline instance and accesses its state through the reference.
    """

    def __init__(self, pipeline: AlphaResearchPipeline) -> None:
        self._pipeline = pipeline

    def _eligible_profiles(self) -> list[dict]:
        """Return ADAPTIVE_PROFILES filtered by current account tier."""
        p = self._pipeline
        profile = getattr(p, "user_profile", None) or {}
        return eligible_strategy_profiles(profile)

    def _initial_strategy_profile_index(self) -> int:
        p = self._pipeline
        for index, profile in enumerate(self._eligible_profiles()):
            if (
                profile["region"] == p.config.settings.region
                and profile["universe"] == p.config.settings.universe
                and profile["delay"] == p.config.settings.delay
                and profile["neutralization"] == p.config.settings.neutralization
            ):
                return index
        return 0

    def _current_strategy_profile(self) -> dict:
        p = self._pipeline
        eligible = self._eligible_profiles()
        idx = p.strategy_profile_index % max(len(eligible), 1)
        profile = dict(eligible[idx])
        profile["settings"] = p.config.settings.to_platform_dict()["settings"]
        return profile

    def _maybe_switch_strategy(
        self,
        cycle: int,
        fields: list[dict],
        operators: list[dict],
        pool_by_expression: dict[str, Candidate],
        accepted_candidates: list[Candidate],
        archive_stats: dict[str, int],
    ) -> tuple[list[dict], list[dict]]:
        p = self._pipeline
        if not p.config.budget.adaptive_strategy_enabled:
            return fields, operators
        if p.backtest_slots or p.official_calls_halted:
            return fields, operators
        min_results = max(1, int(p.config.budget.adaptive_min_official_results))
        min_cycles = max(1, int(p.config.budget.adaptive_min_cycles))
        results = p.official_results_since_strategy_switch
        ready_rate = p.ready_since_strategy_switch / max(results, 1)
        chronic_no_candidate = p.cycles_since_strategy_switch >= min_cycles and len(pool_by_expression) < 3
        chronic_official_fail = results >= min_results and ready_rate < float(p.config.budget.adaptive_min_ready_rate)
        if not chronic_no_candidate and not chronic_official_fail:
            return fields, operators
        trigger = "chronic_no_candidate" if chronic_no_candidate else "chronic_official_fail"
        current_profile = self._current_strategy_profile()
        p.strategy_lifecycle.validate(
            current_profile,
            index=p.strategy_profile_index,
            cycle=cycle,
            ready_rate=ready_rate,
            official_results=results,
            pool_size=len(pool_by_expression),
            trigger=trigger,
        )
        p.services.runtime._notify_strategy_plugins(
            "validate",
            current_profile,
            cycle=cycle,
            reason=trigger,
            ready_rate=ready_rate,
            official_results=results,
            pool_size=len(pool_by_expression),
        )

        eligible = self._eligible_profiles()
        n_profiles = len(eligible)
        switch_service = StrategySwitchService()
        decision = switch_service.select_next_index(
            current_index=p.strategy_profile_index,
            eligible_profiles=eligible,
            bandit_rewards=p._bandit_rewards,
            bandit_counts=p._bandit_counts,
        )
        next_idx = int(decision["next_index"])
        mean_rewards = dict(decision.get("mean_rewards") or {})

        application = switch_service.build_application(
            current_index=p.strategy_profile_index,
            next_index=next_idx,
            eligible_profiles=eligible,
        )
        old_idx = application.old_index
        old_profile = application.old_profile
        profile = application.next_profile
        p.strategy_profile_index = application.next_index
        if not application.retained:
            p.strategy_lifecycle.retire(old_profile, index=old_idx, cycle=cycle, reason=trigger)
            p.services.runtime._notify_strategy_plugins("retire", old_profile, cycle=cycle, reason=trigger, profile_index=old_idx)
            p.strategy_lifecycle.mutate(
                old_profile,
                profile,
                parent_index=old_idx,
                child_index=next_idx,
                cycle=cycle,
                reason=trigger,
            )
            p.services.runtime._notify_strategy_plugins(
                "mutate",
                profile,
                cycle=cycle,
                reason=trigger,
                parent_profile=old_profile,
                parent_profile_index=old_idx,
                profile_index=next_idx,
            )
        else:
            p.strategy_lifecycle.propose(profile, index=next_idx, cycle=cycle, reason=f"retained after {trigger}")
            p.services.runtime._notify_strategy_plugins(
                "propose",
                profile,
                cycle=cycle,
                reason=f"retained after {trigger}",
                profile_index=next_idx,
            )
        bandit_note = str(decision.get("mode") or ("exploit" if p._bandit_rewards.get(next_idx) else "cold-start"))
        p.services.runtime._event("bandit_selection",
            f"Bandit {bandit_note}: profile {profile['name']} (idx={next_idx}) "
            f"reward={mean_rewards.get(next_idx, 0):.3f} "
            f"count={p._bandit_counts.get(next_idx, 0)}",
            level="INFO")
        p.config.settings.region = application.settings["region"]
        p.config.settings.universe = application.settings["universe"]
        p.config.settings.delay = application.settings["delay"]
        p.config.settings.neutralization = application.settings["neutralization"]
        setter = getattr(p.api, "set_market_scope", None)
        if callable(setter):
            setter(p.config.settings)
        p.strategy_switch_count += 1
        p.cycles_since_strategy_switch = 0
        p.official_results_since_strategy_switch = 0
        p.ready_since_strategy_switch = 0
        p.official_rejections_since_strategy_switch = 0
        retained_ids = set(switch_service.retained_candidate_ids(list(pool_by_expression.values())))
        for candidate in pool_by_expression.values():
            if candidate.alpha_id in retained_ids:
                candidate.validation = {}
                candidate.lifecycle_status = "candidate_pool_retained"
        p.services.runtime._event(
            "adaptive_strategy_switched",
            f"Switched to {profile['label']}: {profile['reason']}",
            data={"profile": profile, "cycle": cycle},
            level="WARN",
        )
        p.services.runtime._progress(
            "strategy_switch",
            p.strategy_switch_count,
            max(1, len(eligible)),
            f"长期回测未通过，切换到：{profile['label']}。{profile['reason']}",
            data=p._runtime_data(
                cycle,
                rank_candidates(list(pool_by_expression.values())),
                accepted_candidates,
                archive_stats,
                {"strategy_profile": self._current_strategy_profile()},
            ),
        )
        return p.services.context_sync._load_official_context()
