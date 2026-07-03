"""LifecycleStatusNormalizer —— 遗留状态字符串到规范 LifecycleState 的封装器。

按 ``refactor-brain-alpha-six-waves`` 规格 Task 6.1 实现 3 版本弃用时间线：

  * vN   —— 引入 normalizer 并保持向后兼容：遗留字符串静默映射到规范枚举
           （SubTask 6.1.2）。本任务执行 vN，为默认阶段。
  * vN+1 —— 对遗留别名状态发出 ``DeprecationWarning``，由环境变量
           ``BRAIN_ALPHA_LIFECYCLE_DEPRECATION_PHASE=vN+1`` 控制启用，便于
           分阶段灰度（SubTask 6.1.3）。
  * vN+2 —— 规划：移除遗留状态支持，仅保留规范 ``LifecycleState`` enum，
           命中遗留别名时抛 ``ValueError``。本任务不实现该阶段
           （SubTask 6.1.4，仅规划）。

新增状态必须通过规范 ``LifecycleState`` enum（SubTask 6.1.5）。
遗留映射项预期从 30+ 逐步降至 ≤10，随调用方迁移收敛（SubTask 6.1.6）。

数据源：``brain_alpha_ops.candidate_lifecycle._LEGACY_STATUS_MAP``。
本类引用该映射而非复制，确保单一数据源。
"""
from __future__ import annotations

import os
import warnings
from typing import Final

from brain_alpha_ops.candidate_lifecycle import LifecycleState, _LEGACY_STATUS_MAP

# 弃用阶段环境变量名（SubTask 6.1.3：版本开关）。
_DEPRECATION_PHASE_ENV: Final[str] = "BRAIN_ALPHA_LIFECYCLE_DEPRECATION_PHASE"

# 当前默认阶段：vN（静默映射，保持向后兼容）。
_DEFAULT_PHASE: Final[str] = "vN"

# 合法阶段取值。
_VALID_PHASES: Final[frozenset[str]] = frozenset({"vN", "vN+1", "vN+2"})


class LifecycleStatusNormalizer:
    """遗留状态字符串 → 规范 ``LifecycleState`` 的封装器。

    数据源：``_LEGACY_STATUS_MAP``（引用而非复制，保持单一数据源）。

    行为按 ``BRAIN_ALPHA_LIFECYCLE_DEPRECATION_PHASE`` 切换：

      * ``vN``（默认）—— 静默映射（SubTask 6.1.2）。
      * ``vN+1``       —— 对遗留别名发出 ``DeprecationWarning``（SubTask 6.1.3）。
      * ``vN+2``       —— 规划：对遗留别名抛 ``ValueError``（SubTask 6.1.4，未实现）。

    “遗留别名”指映射中键名与规范枚举值不同的条目（如 ``"created"`` →
    ``draft``）；规范名字符串（如 ``"draft"``）视为规范值的字符串形式，
    不视为遗留别名，全阶段静默通过。
    """

    def __init__(self, legacy_map: dict[str, LifecycleState] | None = None) -> None:
        # 引用而非复制，保持 _LEGACY_STATUS_MAP 作为单一数据源（SubTask 6.1.1）。
        self._legacy_map: dict[str, LifecycleState] = (
            legacy_map if legacy_map is not None else _LEGACY_STATUS_MAP
        )

    @staticmethod
    def _current_phase() -> str:
        """读取当前弃用阶段环境变量（默认 vN）。未知值回退到 vN，避免配置笔误阻断生产。"""
        phase = os.environ.get(_DEPRECATION_PHASE_ENV, _DEFAULT_PHASE)
        return phase if phase in _VALID_PHASES else _DEFAULT_PHASE

    @property
    def legacy_map(self) -> dict[str, LifecycleState]:
        """暴露底层遗留映射，供调用方派生集合时复用（不复制，保持单一数据源）。"""
        return self._legacy_map

    def is_legacy(self, status: "str | LifecycleState") -> bool:
        """判断 status 是否为遗留别名字符串。

        规范枚举实例、规范名字符串（如 ``"draft"``）、未知字符串均返回 False；
        仅当 status 是映射中“键名 ≠ 规范值”的别名时返回 True。
        """
        if isinstance(status, LifecycleState):
            return False
        if not isinstance(status, str):
            return False
        mapped = self._legacy_map.get(status)
        if mapped is None:
            return False
        return status != mapped.value

    def normalize(self, status: "str | LifecycleState") -> LifecycleState:
        """将遗留字符串或规范枚举统一映射为规范 ``LifecycleState``。

        * 规范枚举实例直接返回（SubTask 6.1.5：新增状态走 enum）。
        * 命中遗留映射：
            - vN   —— 静默映射（SubTask 6.1.2）。
            - vN+1 —— 仅对遗留别名（键名 ≠ 规范值）发出 ``DeprecationWarning``
                     （SubTask 6.1.3）。
            - vN+2 —— 规划：对遗留别名抛 ``ValueError``（SubTask 6.1.4，未实现）。
        * 未知字符串回退到 ``LifecycleState.draft``，保持与原
          ``_LEGACY_STATUS_MAP.get(current, LifecycleState.draft)`` 一致。
        """
        if isinstance(status, LifecycleState):
            return status
        if isinstance(status, str) and status in self._legacy_map:
            mapped = self._legacy_map[status]
            phase = self._current_phase()
            if phase == "vN+1" and status != mapped.value:
                # 仅对遗留别名发出弃用警告；规范名字符串不警告（SubTask 6.1.3）。
                warnings.warn(
                    f"Legacy lifecycle status {status!r} is deprecated; "
                    f"use the canonical LifecycleState.{mapped.name} enum instead. "
                    f"(phase=vN+1, see SubTask 6.1.3)",
                    DeprecationWarning,
                    stacklevel=2,
                )
            # vN+2 阶段规划：在此对遗留别名抛 ValueError（SubTask 6.1.4，本任务不实现）。
            return mapped
        # 未知字符串回退到 draft（向后兼容原 .get(..., draft) 语义）。
        return LifecycleState.draft


# 模块级单例，供调用方直接复用。
normalizer: LifecycleStatusNormalizer = LifecycleStatusNormalizer()
