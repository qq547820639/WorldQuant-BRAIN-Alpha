from brain_alpha_ops.research.strategy_switch import StrategySwitchService


class CandidateLike:
    def __init__(self, alpha_id, *, simulation_id="", official_metrics=None):
        self.alpha_id = alpha_id
        self.simulation_id = simulation_id
        self.official_metrics = official_metrics


def test_strategy_switch_service_exploits_best_reward():
    service = StrategySwitchService(epsilon=0.0, choice_func=lambda items: items[0])

    decision = service.select_next_index(
        current_index=0,
        eligible_profiles=[{"name": "a"}, {"name": "b"}],
        bandit_rewards={0: [0.1], 1: [0.9, 0.7]},
        bandit_counts={0: 1, 1: 2},
    )

    assert decision["schema_version"] == "strategy_switch_decision.v1"
    assert decision["mode"] == "exploit"
    assert decision["next_index"] == 1
    assert decision["mean_rewards"][1] == 0.8


def test_strategy_switch_service_explores_weighted_profiles():
    values = iter([0.0, 0.01])
    service = StrategySwitchService(epsilon=1.0, random_func=lambda: next(values))

    decision = service.select_next_index(
        current_index=1,
        eligible_profiles=[{"name": "a"}, {"name": "b"}],
        bandit_rewards={},
        bandit_counts={0: 1, 1: 10},
    )

    assert decision["mode"] == "explore"
    assert decision["next_index"] == 0


def test_strategy_switch_service_builds_application_plan():
    service = StrategySwitchService()

    application = service.build_application(
        current_index=0,
        next_index=1,
        eligible_profiles=[
            {"name": "a", "region": "USA", "universe": "TOP3000", "delay": 1, "neutralization": "INDUSTRY"},
            {"name": "b", "region": "GLB", "universe": "TOP500", "delay": 0, "neutralization": "SECTOR"},
        ],
    )

    assert application.retained is False
    assert application.old_profile["name"] == "a"
    assert application.next_profile["name"] == "b"
    assert application.settings == {
        "region": "GLB",
        "universe": "TOP500",
        "delay": 0,
        "neutralization": "SECTOR",
    }


def test_strategy_switch_service_identifies_retained_unsubmitted_candidates():
    service = StrategySwitchService()

    ids = service.retained_candidate_ids(
        [
            CandidateLike("a"),
            CandidateLike("b", simulation_id="sim_1"),
            CandidateLike("c", official_metrics={"sharpe": 1.2}),
        ]
    )

    assert ids == ["a"]
