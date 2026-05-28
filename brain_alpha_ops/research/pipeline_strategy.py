"""Adaptive strategy switching helpers for AlphaResearchPipeline."""

from __future__ import annotations

from brain_alpha_ops.models import Candidate

from .pipeline_helpers import rank_candidates
from .production_context import eligible_strategy_profiles
from .strategy_switch import StrategySwitchService


class PipelineStrategyMixin:
    def _eligible_profiles(self) -> list[dict]:
        """Return ADAPTIVE_PROFILES filtered by current account tier."""
        profile = getattr(self, "user_profile", None) or {}
        return eligible_strategy_profiles(profile)

    def _initial_strategy_profile_index(self) -> int:
        for index, profile in enumerate(self._eligible_profiles()):
            if (
                profile["region"] == self.config.settings.region
                and profile["universe"] == self.config.settings.universe
                and profile["delay"] == self.config.settings.delay
                and profile["neutralization"] == self.config.settings.neutralization
            ):
                return index
        return 0

    def _current_strategy_profile(self) -> dict:
        eligible = self._eligible_profiles()
        idx = self.strategy_profile_index % max(len(eligible), 1)
        profile = dict(eligible[idx])
        profile["settings"] = self.config.settings.to_platform_dict()["settings"]
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
        if not self.config.budget.adaptive_strategy_enabled:
            return fields, operators
        if self.backtest_slots or self.official_calls_halted:
            return fields, operators
        min_results = max(1, int(self.config.budget.adaptive_min_official_results))
        min_cycles = max(1, int(self.config.budget.adaptive_min_cycles))
        results = self.official_results_since_strategy_switch
        ready_rate = self.ready_since_strategy_switch / max(results, 1)
        chronic_no_candidate = self.cycles_since_strategy_switch >= min_cycles and len(pool_by_expression) < 3
        chronic_official_fail = results >= min_results and ready_rate < float(self.config.budget.adaptive_min_ready_rate)
        if not chronic_no_candidate and not chronic_official_fail:
            return fields, operators
        trigger = "chronic_no_candidate" if chronic_no_candidate else "chronic_official_fail"
        current_profile = self._current_strategy_profile()
        self.strategy_lifecycle.validate(
            current_profile,
            index=self.strategy_profile_index,
            cycle=cycle,
            ready_rate=ready_rate,
            official_results=results,
            pool_size=len(pool_by_expression),
            trigger=trigger,
        )
        self._notify_strategy_plugins(
            "validate",
            current_profile,
            cycle=cycle,
            reason=trigger,
            ready_rate=ready_rate,
            official_results=results,
            pool_size=len(pool_by_expression),
        )

        # P3-1: Epsilon-greedy multi-armed bandit for strategy selection
        #   - epsilon=0.20: 20% random exploration, 80% best-known exploitation
        #   - reward = avg_sharpe × (0.5 + 0.5 × pass_rate)
        #   - cold-start: first selection per profile uses round-robin
        eligible = self._eligible_profiles()
        n_profiles = len(eligible)
        switch_service = StrategySwitchService()
        decision = switch_service.select_next_index(
            current_index=self.strategy_profile_index,
            eligible_profiles=eligible,
            bandit_rewards=self._bandit_rewards,
            bandit_counts=self._bandit_counts,
        )
        next_idx = int(decision["next_index"])
        mean_rewards = dict(decision.get("mean_rewards") or {})

        application = switch_service.build_application(
            current_index=self.strategy_profile_index,
            next_index=next_idx,
            eligible_profiles=eligible,
        )
        old_idx = application.old_index
        old_profile = application.old_profile
        profile = application.next_profile
        self.strategy_profile_index = application.next_index
        if not application.retained:
            self.strategy_lifecycle.retire(old_profile, index=old_idx, cycle=cycle, reason=trigger)
            self._notify_strategy_plugins("retire", old_profile, cycle=cycle, reason=trigger, profile_index=old_idx)
            self.strategy_lifecycle.mutate(
                old_profile,
                profile,
                parent_index=old_idx,
                child_index=next_idx,
                cycle=cycle,
                reason=trigger,
            )
            self._notify_strategy_plugins(
                "mutate",
                profile,
                cycle=cycle,
                reason=trigger,
                parent_profile=old_profile,
                parent_profile_index=old_idx,
                profile_index=next_idx,
            )
        else:
            self.strategy_lifecycle.propose(profile, index=next_idx, cycle=cycle, reason=f"retained after {trigger}")
            self._notify_strategy_plugins(
                "propose",
                profile,
                cycle=cycle,
                reason=f"retained after {trigger}",
                profile_index=next_idx,
            )
        bandit_note = str(decision.get("mode") or ("exploit" if self._bandit_rewards.get(next_idx) else "cold-start"))
        self._event("bandit_selection",
            f"Bandit {bandit_note}: profile {profile['name']} (idx={next_idx}) "
            f"reward={mean_rewards.get(next_idx, 0):.3f} "
            f"count={self._bandit_counts.get(next_idx, 0)}",
            level="INFO")
        self.config.settings.region = application.settings["region"]
        self.config.settings.universe = application.settings["universe"]
        self.config.settings.delay = application.settings["delay"]
        self.config.settings.neutralization = application.settings["neutralization"]
        setter = getattr(self.api, "set_market_scope", None)
        if callable(setter):
            setter(self.config.settings)
        self.strategy_switch_count += 1
        self.cycles_since_strategy_switch = 0
        self.official_results_since_strategy_switch = 0
        self.ready_since_strategy_switch = 0
        self.official_rejections_since_strategy_switch = 0
        retained_ids = set(switch_service.retained_candidate_ids(list(pool_by_expression.values())))
        for candidate in pool_by_expression.values():
            if candidate.alpha_id in retained_ids:
                candidate.validation = {}
                candidate.lifecycle_status = "candidate_pool_retained"
        self._event(
            "adaptive_strategy_switched",
            f"Switched to {profile['label']}: {profile['reason']}",
            data={"profile": profile, "cycle": cycle},
            level="WARN",
        )
        self._progress(
            "strategy_switch",
            self.strategy_switch_count,
            max(1, len(eligible)),
            f"长期回测未通过，切换到：{profile['label']}。{profile['reason']}",
            data=self._runtime_data(
                cycle,
                rank_candidates(list(pool_by_expression.values())),
                accepted_candidates,
                archive_stats,
                {"strategy_profile": self._current_strategy_profile()},
            ),
        )
        return self._load_official_context()
