import textwrap

from brain_alpha_ops.brain_api.mock import MockBrainAPI
from brain_alpha_ops.config import OpsConfig, ResearchBudget
from brain_alpha_ops.research.pipeline import AlphaResearchPipeline
from brain_alpha_ops.research.strategy_plugins import StrategyPluginRegistry


def test_strategy_plugin_registry_loads_and_notifies_plugin(tmp_path, monkeypatch):
    plugin_path = tmp_path / "demo_strategy_plugin.py"
    plugin_path.write_text(
        textwrap.dedent(
            """
            class DemoStrategyPlugin:
                name = "demo"

                def propose(self, context):
                    return {"seen_cycle": context["cycle"]}

                def validate(self, profile, context):
                    return {"profile": profile.get("name", ""), "reason": context.get("reason", "")}

                def mutate(self, profile, context):
                    return {"next_profile": profile.get("name", "")}

                def retire(self, profile, context):
                    return {"retired_profile": profile.get("name", "")}

            plugin = DemoStrategyPlugin()
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    registry = StrategyPluginRegistry.from_specs(["demo_strategy_plugin:plugin"])
    rows = registry.notify("propose", context={"cycle": 3})
    summary = registry.summary()

    assert registry.names() == ["demo"]
    assert rows[0]["status"] == "ok"
    assert rows[0]["result"]["seen_cycle"] == 3
    assert summary["enabled_count"] == 1
    assert summary["runtime_events"][0]["action"] == "propose"
    assert summary["runtime_errors"] == []


def test_example_strategy_plugin_spec_loads():
    registry = StrategyPluginRegistry.from_specs(
        ["brain_alpha_ops.examples.strategy_plugin:ConservativeMeanReversionPlugin"]
    )
    rows = registry.notify("propose", context={"cycle": 2})

    assert registry.names() == ["conservative_mean_reversion"]
    assert rows[0]["status"] == "ok"
    assert rows[0]["result"]["profile"]["family"] == "mean_reversion"


def test_strategy_plugin_registry_records_load_and_runtime_errors(tmp_path, monkeypatch):
    plugin_path = tmp_path / "bad_strategy_plugin.py"
    plugin_path.write_text(
        textwrap.dedent(
            """
            class IncompletePlugin:
                name = "incomplete"

                def propose(self, context):
                    return {}

            class RuntimeFailingPlugin:
                name = "runtime_fail"

                def propose(self, context):
                    raise RuntimeError("boom")

                def validate(self, profile, context):
                    return {}

                def mutate(self, profile, context):
                    return {}

                def retire(self, profile, context):
                    return {}
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    registry = StrategyPluginRegistry.from_specs(
        ["bad_strategy_plugin:IncompletePlugin", "bad_strategy_plugin:RuntimeFailingPlugin"]
    )
    rows = registry.notify("propose", context={"cycle": 1})
    summary = registry.summary()

    assert summary["enabled_count"] == 1
    assert summary["load_errors"]
    assert "missing methods" in summary["load_errors"][0]["error"]
    assert rows[0]["status"] == "error"
    assert summary["runtime_errors"][0]["plugin"] == "runtime_fail"


def test_pipeline_summary_exposes_strategy_plugin_runtime_state(tmp_path, monkeypatch):
    plugin_path = tmp_path / "pipeline_strategy_plugin.py"
    plugin_path.write_text(
        textwrap.dedent(
            """
            class PipelinePlugin:
                name = "pipeline_demo"

                def propose(self, context):
                    return {"cycle": context["cycle"], "profile_index": context["active_profile_index"]}

                def validate(self, profile, context):
                    return {}

                def mutate(self, profile, context):
                    return {}

                def retire(self, profile, context):
                    return {}
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    config = OpsConfig(
        budget=ResearchBudget(
            max_candidates_per_cycle=4,
            max_official_validations_per_cycle=0,
            max_official_simulations_per_cycle=0,
            max_cycles=1,
            strategy_plugins_enabled=True,
            strategy_plugin_specs=["pipeline_strategy_plugin:PipelinePlugin"],
        ),
        storage_dir=str(tmp_path / "data"),
    )

    result = AlphaResearchPipeline(config=config, api=MockBrainAPI()).run(auto_submit=False)
    plugin_summary = result.summary["strategy_plugins"]

    assert plugin_summary["enabled"] is True
    assert plugin_summary["enabled_count"] == 1
    assert plugin_summary["plugin_names"] == ["pipeline_demo"]
    assert plugin_summary["runtime_events"][0]["action"] == "propose"
