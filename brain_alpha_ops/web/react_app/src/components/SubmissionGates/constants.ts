export interface BlockerAction {
  label: string;
  description: string;
  view?: string;
  url?: string;
  action_type: "navigate" | "external_link" | "info";
}

export const BLOCKER_ACTION_MAP: Record<string, BlockerAction> = {
  missing_official_alpha_id: {
    label: "运行官方验证",
    description: "前往候选管理，对该候选运行官方验证以获取官方 Alpha ID",
    view: "candidates",
    action_type: "navigate",
  },
  missing_official_metrics: {
    label: "运行官方仿真",
    description: "前往候选管理，对该候选运行官方仿真获取完整指标",
    view: "candidates",
    action_type: "navigate",
  },
  missing_official_metric_fields: {
    label: "补充官方指标",
    description: "前往候选管理，为该候选补充缺失的官方指标字段",
    view: "candidates",
    action_type: "navigate",
  },
  official_pass_fail_not_pass: {
    label: "优化候选",
    description: "该候选的官方检查为 NOT PASS，需要继续优化",
    view: "candidates",
    action_type: "navigate",
  },
  decision_band_not_submit_candidate: {
    label: "继续评分与筛选",
    description: "当前候选尚未进入提交候选带，需要继续评分和筛选",
    view: "scoring",
    action_type: "navigate",
  },
  missing_quality_diagnosis: {
    label: "运行质量检查",
    description: "运行质量诊断以获取完整的阻断原因分析",
    view: "quality_check",
    action_type: "navigate",
  },
  high_cloud_similarity: {
    label: "多样化表达式",
    description: "云端相似度过高，需要生成与众不同的表达式",
    view: "candidates",
    action_type: "navigate",
  },
  missing_scientific_audit: {
    label: "补齐科学审计",
    description: "前往候选管理补齐科学审计证据",
    view: "candidates",
    action_type: "navigate",
  },
  no_submit_ready_candidate: {
    label: "继续候选生成与验证",
    description: "暂无提交就绪候选，需要继续生成、验证、仿真流程",
    view: "candidates",
    action_type: "navigate",
  },
  not_submission_ready: {
    label: "完成提交前检查",
    description: "该 Alpha 尚未达到可提交状态，请先在达标列表完成检查",
    view: "quality_check",
    action_type: "navigate",
  },
  production_decision_blocked: {
    label: "复核生产决策",
    description: "生产决策仍阻断，需要复核并处理阻断原因",
    view: "candidates",
    action_type: "navigate",
  },
  local_quality_failed: {
    label: "修复本地质量问题",
    description: "本地质量检查未通过，需要修复后重新评估",
    view: "candidates",
    action_type: "navigate",
  },
  local_backtest_failed: {
    label: "修复本地回测",
    description: "本地回测未通过，检查表达式和数据集后重试",
    view: "candidates",
    action_type: "navigate",
  },
  missing_cloud_similarity: {
    label: "同步云端数据",
    description: "缺少云端相似度证据，请先同步云端 Alpha 数据",
    view: "official_operations",
    action_type: "navigate",
  },
  lifecycle_history_blocked: {
    label: "处理归档候选",
    description: "存在历史归档风险，需要先归档或清理",
    view: "lifecycle",
    action_type: "navigate",
  },
  lifecycle_history_failed: {
    label: "返工失败候选",
    description: "存在历史返工风险，需要先处理失败记录",
    view: "lifecycle",
    action_type: "navigate",
  },
  official_context_proof_failed: {
    label: "刷新官方上下文",
    description: "官方上下文证明未通过，前往官方同步页面刷新",
    view: "official_operations",
    action_type: "navigate",
  },
  score_below_official_simulation_threshold: {
    label: "优化候选分数",
    description: "未达到官方仿真分数门槛，需要继续优化",
    view: "candidates",
    action_type: "navigate",
  },
};
