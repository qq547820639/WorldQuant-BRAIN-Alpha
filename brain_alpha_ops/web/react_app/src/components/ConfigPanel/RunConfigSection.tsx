import type { ReactNode } from "react";
import {
  MAX_CONFIG_TEXT_LENGTH,
  DEFAULT_REGION_OPTIONS,
  DEFAULT_UNIVERSE_OPTIONS,
  DEFAULT_DELAY_OPTIONS,
  DEFAULT_NEUTRALIZATION_OPTIONS,
  DEFAULT_INSTRUMENT_TYPE_OPTIONS,
  DEFAULT_PASTEURIZATION_OPTIONS,
  DEFAULT_UNIT_HANDLING_OPTIONS,
  DEFAULT_NAN_HANDLING_OPTIONS,
  DEFAULT_LANGUAGE_OPTIONS,
  DEFAULT_ALPHA_TYPE_OPTIONS,
  type ConfigForm,
  type ConfigSchema,
  sanitizeConfigText,
} from "./utils";
import {
  ConfigSection,
  TextField,
  NumberField,
  SelectField,
  CheckboxField,
  ConfigValue,
} from "./ConfigFormFields";
import ScoringWeightModal from "./ScoringWeightModal";
import { useThemeContext } from "@/components/ThemeProvider";

interface RunConfigSectionProps {
  form: ConfigForm;
  schema: ConfigSchema | undefined;
  datasetChoices: Array<{ value: string; label: string }>;
  scoring:
    | {
        prior_layer_weight?: number;
        empirical_layer_weight?: number;
        checklist_layer_weight?: number;
        market_regime?: string;
      }
    | undefined;
  showWeightModal: boolean;
  onUpdate: <K extends keyof ConfigForm>(key: K, value: ConfigForm[K]) => void;
  onShowWeightModal: (show: boolean) => void;
}

const FIELD_HELP: Record<string, { what: string; recommendation: string; risk: string }> = {
  region: {
    what: "区域决定了 Alpha 适用的股票市场。USA 针对美国市场，EUR 针对欧洲，GLOBAL 覆盖全球。",
    recommendation: "推荐从 USA (美国) 开始，这是流动性最好的市场。",
    risk: "切换区域可能导致已有候选不再适用。",
  },
  universe: {
    what: "股票池大小决定了 Alpha 覆盖的股票数量。TOP3000 覆盖最大的 3000 只股票。",
    recommendation: "推荐 TOP3000，足够的股票数能保证统计显著性。",
    risk: "股票池越小，Alpha 越容易被极端值影响。",
  },
  delay: {
    what: "延迟（天）决定了信号从产生到可交易的时间差。Delay-1 表示使用昨天的信号今天交易。",
    recommendation: "推荐 1 天延迟，这是最标准的设置。",
    risk: "延迟过短可能引入数据窥探偏差。",
  },
  decay: {
    what: "衰减系数控制历史数据的重要性递减速度。decay=10 表示权重每 10 天衰减一半。",
    recommendation: "推荐 decay=10，这是 BRAIN 平台最常用的设置。",
    risk: "decay 太小可能过度反应近期噪音，太大可能错过趋势变化。",
  },
  neutralization: {
    what: "中性化消除特定因子（如行业、市值）对 Alpha 的影响。SUBINDUSTRY 表示在子行业内中性化。",
    recommendation: "推荐 SUBINDUSTRY，平衡了去偏效果和信号保留。",
    risk: "过度中性化可能把有用的信号也消除掉。",
  },
  pasteurization: {
    what: "数据净化自动处理异常值和缺失数据，ON 表示启用 BRAIN 平台的自动清理。",
    recommendation: "推荐保持 ON，避免脏数据污染 Alpha 表现。",
    risk: "关闭数据净化可能产生虚假的高分 Alpha（实际不可靠）。",
  },
  unitHandling: {
    what: "单位处理决定如何处理不同股票的不同价格量级。VERIFY 表示系统会自动检查并统一单位。",
    recommendation: "推荐 VERIFY，确保跨股票比较有意义。",
    risk: "关闭单位处理可能导致不同价格量级的股票不可比较。",
  },
  nanHandling: {
    what: "空值处理决定如何处理缺失数据。ON 表示自动填充或排除空值。",
    recommendation: "推荐保持 ON。",
    risk: "关闭后空值可能导致 Alpha 计算异常。",
  },
  minSharpe: {
    what: "最低 Sharpe 比率门禁。Sharpe = 收益 / 波动率，衡量风险调整后收益。",
    recommendation: "BRAIN 平台标准：Delay-1 最低 1.25，Delay-0 最低 2.0。",
    risk: "调低门禁可能通过更多低质量 Alpha。",
  },
  minFitness: {
    what: "最低 Fitness 门禁。Fitness = Sharpe × √(|Returns|/max(Turnover, 0.125))，综合衡量收益和换手率。",
    recommendation: "BRAIN 平台标准：Delay-1 最低 1.0，Delay-0 最低 1.3。",
    risk: "调低门禁可能通过更多低换手性价比的 Alpha。",
  },
  maxSelfCorrelation: {
    what: "最大自相关门禁。限制提交的 Alpha 与自己已有 Alpha 的相似度。",
    recommendation: "BRAIN 平台标准：< 0.70。",
    risk: "自相关过高的 Alpha 会被 BRAIN 平台拒绝。",
  },
};

const formatHelp = (help: (typeof FIELD_HELP)[string]) =>
  `${help.what}\n\n推荐: ${help.recommendation}\n⚠️ ${help.risk}`;

const HelpIcon = ({ help }: { help: (typeof FIELD_HELP)[string] }) => (
  <span
    title={formatHelp(help)}
    className="cursor-help ml-1 text-xs opacity-60 hover:opacity-100"
    aria-label="字段帮助信息"
    role="img"
  >
    ❓
  </span>
);

const optionValues = (
  settingsOptions: ConfigSchema["settings_options"] | undefined,
  key: string,
  currentValue: string,
  fallback: string[],
): string[] => {
  const values = settingsOptions?.[key]?.map(String).filter(Boolean);
  const options = values?.length ? values : fallback;
  if (currentValue && !options.includes(currentValue)) {
    return [currentValue, ...options];
  }
  return options;
};

const helpContent = (key: string): ReactNode => {
  const entry = FIELD_HELP[key];
  return entry ? <HelpIcon help={entry} /> : null;
};

export default function RunConfigSection({
  form,
  schema,
  datasetChoices,
  scoring,
  showWeightModal,
  onUpdate,
  onShowWeightModal,
}: RunConfigSectionProps) {
  const { isDark, toggleTheme } = useThemeContext();
  const options = schema?.settings_options;

  return (
    <>
      <ConfigSection
        title="BRAIN 设置"
        description="字段和选项来自后端公开的官方能力集校验，不在前端自定义扩展。"
      >
        <details open className="col-span-full group/config-details mb-2">
          <summary className="text-sm font-medium text-text-secondary cursor-pointer py-1 select-none hover:text-text-primary transition-colors">
            基础参数
          </summary>
          <div className="mt-3 grid grid-cols-1 gap-x-5 gap-y-4 md:grid-cols-2">
            <SelectField
              label="资产类型"
              value={form.instrumentType}
              options={optionValues(options, "instrumentType", form.instrumentType, DEFAULT_INSTRUMENT_TYPE_OPTIONS)}
              onChange={(value) => onUpdate("instrumentType", value)}
            />
            <SelectField
              label="区域"
              value={form.region}
              options={optionValues(options, "region", form.region, DEFAULT_REGION_OPTIONS)}
              help={helpContent("region")}
              onChange={(value) => onUpdate("region", value)}
            />
            <SelectField
              label="股票池"
              value={form.universe}
              options={optionValues(options, "universe", form.universe, DEFAULT_UNIVERSE_OPTIONS)}
              help={helpContent("universe")}
              onChange={(value) => onUpdate("universe", value)}
            />
            <SelectField
              label="延迟"
              value={String(form.delay)}
              options={optionValues(options, "delay", String(form.delay), DEFAULT_DELAY_OPTIONS)}
              help={helpContent("delay")}
              onChange={(value) => onUpdate("delay", Number(value))}
            />
            <NumberField
              label="衰减"
              value={form.decay}
              min={0}
              step={1}
              help={helpContent("decay")}
              onChange={(value) => onUpdate("decay", value)}
            />
            {datasetChoices.length ? (
              <SelectField
                label="数据集"
                value={form.dataset}
                options={datasetChoices}
                placeholder="自动选择"
                onChange={(value) => onUpdate("dataset", value)}
              />
            ) : (
              <TextField
                label="数据集"
                value={form.dataset}
                maxLength={MAX_CONFIG_TEXT_LENGTH}
                onChange={(value) => onUpdate("dataset", sanitizeConfigText(value))}
              />
            )}
            <SelectField
              label="Alpha 类型"
              value={form.alphaType}
              options={optionValues(options, "type", form.alphaType, DEFAULT_ALPHA_TYPE_OPTIONS)}
              onChange={(value) => onUpdate("alphaType", value)}
            />
          </div>
        </details>
        <details className="col-span-full group/config-details mb-2">
          <summary className="text-sm font-medium text-text-secondary cursor-pointer py-1 select-none hover:text-text-primary transition-colors">
            高级参数
          </summary>
          <div className="mt-3 grid grid-cols-1 gap-x-5 gap-y-4 md:grid-cols-2">
            <SelectField
              label="中性化"
              value={form.neutralization}
              options={optionValues(options, "neutralization", form.neutralization, DEFAULT_NEUTRALIZATION_OPTIONS)}
              help={helpContent("neutralization")}
              onChange={(value) => onUpdate("neutralization", value)}
            />
            <SelectField
              label="数据净化"
              value={form.pasteurization}
              options={optionValues(options, "pasteurization", form.pasteurization, DEFAULT_PASTEURIZATION_OPTIONS)}
              help={helpContent("pasteurization")}
              onChange={(value) => onUpdate("pasteurization", value)}
            />
            <SelectField
              label="单位处理"
              value={form.unitHandling}
              options={optionValues(options, "unitHandling", form.unitHandling, DEFAULT_UNIT_HANDLING_OPTIONS)}
              help={helpContent("unitHandling")}
              onChange={(value) => onUpdate("unitHandling", value)}
            />
            <SelectField
              label="空值处理"
              value={form.nanHandling}
              options={optionValues(options, "nanHandling", form.nanHandling, DEFAULT_NAN_HANDLING_OPTIONS)}
              help={helpContent("nanHandling")}
              onChange={(value) => onUpdate("nanHandling", value)}
            />
            <SelectField
              label="语言"
              value={form.language}
              options={optionValues(options, "language", form.language, DEFAULT_LANGUAGE_OPTIONS)}
              onChange={(value) => onUpdate("language", value)}
            />
          </div>
        </details>
      </ConfigSection>

      <ConfigSection
        title="预算控制"
        description="用于限制单次生产运行的候选数量、轮次和回测批量。"
      >
        <NumberField
          label="每轮最大候选数"
          value={form.candidates}
          min={1}
          max={1000}
          step={1}
          debounceMs={300}
          onChange={(value) => onUpdate("candidates", value)}
        />
        <NumberField
          label="最大轮次"
          value={form.cycles}
          min={1}
          max={10000}
          step={1}
          debounceMs={300}
          onChange={(value) => onUpdate("cycles", value)}
        />
        <NumberField
          label="候选池大小"
          value={form.poolSize}
          min={1}
          max={5000}
          step={1}
          debounceMs={300}
          onChange={(value) => onUpdate("poolSize", value)}
        />
        <NumberField
          label="回测批处理大小"
          value={form.backtestBatchSize}
          min={1}
          max={100}
          step={1}
          debounceMs={300}
          onChange={(value) => onUpdate("backtestBatchSize", value)}
        />
        <div>
          <CheckboxField
            label="每次运行前强制云端同步"
            checked={form.requireCloudSync}
            onChange={(value) => onUpdate("requireCloudSync", value)}
          />
          <p className="mt-1 text-xs leading-5 text-text-tertiary">
            默认关闭：首次无缓存时自动同步，之后直接使用本地缓存；开启后，每次生产运行前都会重新拉取云端 Alpha 与官方能力集。
          </p>
        </div>
      </ConfigSection>

      <ConfigSection
        title="质量阈值"
        description="提交前门禁，低于阈值的候选只能进入研究或优化状态。"
      >
        <NumberField
          label="最低夏普比率"
          value={form.minSharpe}
          min={0}
          step={0.01}
          help={helpContent("minSharpe")}
          debounceMs={300}
          onChange={(value) => onUpdate("minSharpe", value)}
        />
        <NumberField
          label="最低适应度"
          value={form.minFitness}
          min={0}
          step={0.01}
          help={helpContent("minFitness")}
          debounceMs={300}
          onChange={(value) => onUpdate("minFitness", value)}
        />
        <NumberField
          label="最低换手率"
          value={form.minTurnover}
          min={0}
          max={1}
          step={0.01}
          debounceMs={300}
          onChange={(value) => onUpdate("minTurnover", value)}
        />
        <NumberField
          label="最高换手率"
          value={form.platformMaxTurnover}
          min={0}
          max={1}
          step={0.01}
          debounceMs={300}
          onChange={(value) => onUpdate("platformMaxTurnover", value)}
        />
        <NumberField
          label="最大自相关性"
          value={form.maxSelfCorrelation}
          min={0}
          max={1}
          step={0.01}
          help={helpContent("maxSelfCorrelation")}
          debounceMs={300}
          onChange={(value) => onUpdate("maxSelfCorrelation", value)}
        />
        <NumberField
          label="最大权重集中度"
          value={form.maxWeightConcentration}
          min={0}
          max={1}
          step={0.01}
          debounceMs={300}
          onChange={(value) => onUpdate("maxWeightConcentration", value)}
        />
      </ConfigSection>

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

      {showWeightModal && (
        <ScoringWeightModal
          schema={schema}
          scoring={scoring}
          onClose={() => onShowWeightModal(false)}
        />
      )}
    </>
  );
}
