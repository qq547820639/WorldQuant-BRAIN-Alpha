import { useThemeContext } from "@/components/ThemeProvider";
import {
  ConfigSection,
  ConfigValue,
  CheckboxField,
} from "./ConfigFormFields";

interface ScoringConfigGroupProps {
  scoring:
    | {
        prior_layer_weight?: number;
        empirical_layer_weight?: number;
        checklist_layer_weight?: number;
        market_regime?: string;
      }
    | undefined;
  onShowWeightModal: (show: boolean) => void;
}

export default function ScoringConfigGroup({
  scoring,
  onShowWeightModal,
}: ScoringConfigGroupProps) {
  const { isDark, toggleTheme } = useThemeContext();

  return (
    <>
      <ConfigSection
        title="评分配置"
        description="当前评分层权重为只读展示，避免和官方门禁配置混淆。"
      >
        <ConfigValue label="先验权重" value={scoring?.prior_layer_weight} />
        <ConfigValue label="经验权重" value={scoring?.empirical_layer_weight} />
        <ConfigValue label="检查清单权重" value={scoring?.checklist_layer_weight} />
        <ConfigValue label="市场状态" value={scoring?.market_regime} />
        <div className="col-span-full mt-2">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => onShowWeightModal(true)}
          >
            查看详细权重
          </button>
        </div>
      </ConfigSection>

      <ConfigSection
        title="环境设置"
        description="本地 Web 页面只允许保存非提交运行配置；真实提交必须走单独的人工确认流程。"
      >
        <div className="col-span-full">
          <CheckboxField label="暗色模式" checked={isDark} onChange={toggleTheme} />
          <p className="mt-1 text-xs leading-5 text-text-tertiary">
            切换亮色/暗色主题，设置会保存在本地浏览器中。
          </p>
        </div>
        <ConfigValue label="自动提交" value="关闭（Web 保存强制）" />
      </ConfigSection>
    </>
  );
}
