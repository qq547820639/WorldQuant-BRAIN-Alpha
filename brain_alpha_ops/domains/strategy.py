"""Strategy domain — lifecycle, plugins, dataset selection (v4.0)."""
from brain_alpha_ops.research.dataset_selector import DatasetSelector
from brain_alpha_ops.research.strategy_lifecycle import StrategyLifecycleManager
from brain_alpha_ops.research.strategy_plugins import (
    StrategyPluginRegistry,
    load_strategy_plugin,
)
from brain_alpha_ops.research.strategy_switch import StrategySwitch
