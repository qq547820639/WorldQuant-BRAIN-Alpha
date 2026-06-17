import { describe, expect, it } from "vitest";
import { readinessNextActionLabel, readinessProductionGapLabel, readinessReasonLabel } from "@/helpers/readinessLabels";

describe("readinessLabels", () => {
  it("labels shared submit-readiness blockers", () => {
    expect(readinessReasonLabel("missing_official_metrics")).toBe("缺少官方仿真指标");
    expect(readinessReasonLabel("candidate_family_not_submit_band")).toBe("候选族尚未进入复核带");
    expect(readinessReasonLabel("score_below_official_simulation_threshold")).toBe("未达到官方仿真分数门槛");
  });

  it("labels representative official evidence blockers", () => {
    expect(readinessReasonLabel("missing_official_alpha_id")).toBe("缺少官方 Alpha ID");
    expect(readinessReasonLabel("candidate_family_missing_official_metrics")).toBe("候选族缺少官方仿真指标");
    expect(readinessReasonLabel("official_validation_without_simulation")).toBe("有官方验证但缺少官方仿真指标");
  });

  it("labels decision band values used by readiness summaries", () => {
    expect(readinessReasonLabel("decision_band_not_submit_candidate")).toBe("评分决策仍非提交候选");
    expect(readinessReasonLabel("research_only")).toBe("仅限研究");
    expect(readinessReasonLabel("optimize")).toBe("需要继续优化");
    expect(readinessReasonLabel("submit_candidate")).toBe("提交前复核候选");
  });

  it("labels lifecycle and local queue blockers", () => {
    expect(readinessReasonLabel("lifecycle_history_blocked")).toBe("历史生命周期要求归档");
    expect(readinessReasonLabel("latest_candidate_lifecycle_history_failed")).toBe("最新候选存在历史返工风险");
    expect(readinessReasonLabel("local_quality_failed")).toBe("本地质量未通过");
    expect(readinessReasonLabel("local_candidate_invalid")).toBe("本地候选未通过");
    expect(readinessReasonLabel("expression_high_turnover_generation_risk")).toBe("表达式存在高换手风险");
  });

  it("labels scientific audit readiness blockers", () => {
    expect(readinessReasonLabel("missing_scientific_audit")).toBe("缺少科学审计证据");
    expect(readinessReasonLabel("latest_candidate_scientific_audit_test_feedback_used"))
      .toBe("最新候选科学审计含测试反馈");
    expect(readinessReasonLabel("candidate_family_scientific_audit_submit_boundary_breached"))
      .toBe("候选族科学审计提交边界异常");
  });

  it("hides unknown reasons behind safe fallback copy", () => {
    expect(readinessReasonLabel("new_backend_reason")).toBe("存在未分类阻断原因");
    expect(readinessReasonLabel("")).toBe("-");
    expect(readinessReasonLabel("", "无")).toBe("无");
    expect(readinessReasonLabel(null)).toBe("-");
    expect(readinessReasonLabel(undefined, "未知")).toBe("未知");
  });

  it("labels shared submit-readiness next actions", () => {
    expect(readinessNextActionLabel("resolve local blockers before submit review"))
      .toBe("先修复本地阻断，再进入提交复核");
    expect(readinessNextActionLabel("run official simulation/check in a trusted environment"))
      .toBe("在可信环境运行官方仿真/检查");
    expect(readinessNextActionLabel("new backend action")).toBe("继续根据阻断复核结果处理");
    expect(readinessNextActionLabel("", "无")).toBe("无");
  });

  it("hides unknown production-gap messages behind safe fallback copy", () => {
    expect(readinessProductionGapLabel({ code: "missing_official_metrics", message: "raw backend detail" }))
      .toBe("缺少官方仿真指标");
    expect(readinessProductionGapLabel({ message: "raw backend-only production gap" }))
      .toBe("存在未分类生产缺口");
    expect(readinessProductionGapLabel({ code: "new_backend_gap", message: "raw backend detail" }))
      .toBe("存在未分类生产缺口");
    expect(readinessProductionGapLabel(null, "无生产缺口")).toBe("无生产缺口");
  });
});
