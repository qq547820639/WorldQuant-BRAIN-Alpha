/** ConfigPanel run-parameter sections: basic, advanced, scoring, and the
 *  composition entry that wires them together with the scoring-weight modal.
 *
 *  Merges the previously separate BasicConfigGroup.tsx, AdvancedConfigGroup.tsx,
 *  ScoringConfigGroup.tsx, and RunConfigSection.tsx into a single module.
 *  All component implementations are preserved verbatim; only the module
 *  boundary changed. */

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
} from './utils';
import {
  ConfigSection,
  TextField,
  NumberField,
  SelectField,
  CheckboxField,
  ConfigValue,
  helpContent,
} from './ConfigFormFields';
import { useThemeContext } from '@/components/ThemeProvider';
import { ScoringWeightModal } from './ConfigPanelCredentials';

// ──────────────────────────────────────────────────────────────────────────
// BasicConfigGroup — BRAIN settings + budget controls
// ──────────────────────────────────────────────────────────────────────────

interface BasicConfigGroupProps {
  form: ConfigForm;
  schema: ConfigSchema | undefined;
  datasetChoices: Array<{ value: string; label: string }>;
  onUpdate: <K extends keyof ConfigForm>(key: K, value: ConfigForm[K]) => void;
}

const optionValues = (
  settingsOptions: ConfigSchema['settings_options'] | undefined,
  key: string,
  currentValue: string,
  fallback: string[]
): string[] => {
  const values = settingsOptions?.[key]?.map(String).filter(Boolean);
  const options = values?.length ? values : fallback;
  if (currentValue && !options.includes(currentValue)) {
    return [currentValue, ...options];
  }
  return options;
};

export function BasicConfigGroup({
  form,
  schema,
  datasetChoices,
  onUpdate,
}: BasicConfigGroupProps) {
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
              options={optionValues(
                options,
                'instrumentType',
                form.instrumentType,
                DEFAULT_INSTRUMENT_TYPE_OPTIONS
              )}
              onChange={(value) => onUpdate('instrumentType', value)}
            />
            <SelectField
              label="区域"
              value={form.region}
              options={optionValues(options, 'region', form.region, DEFAULT_REGION_OPTIONS)}
              help={helpContent('region')}
              onChange={(value) => onUpdate('region', value)}
            />
            <SelectField
              label="股票池"
              value={form.universe}
              options={optionValues(options, 'universe', form.universe, DEFAULT_UNIVERSE_OPTIONS)}
              help={helpContent('universe')}
              onChange={(value) => onUpdate('universe', value)}
            />
            <SelectField
              label="延迟"
              value={String(form.delay)}
              options={optionValues(options, 'delay', String(form.delay), DEFAULT_DELAY_OPTIONS)}
              help={helpContent('delay')}
              onChange={(value) => onUpdate('delay', Number(value))}
            />
            <NumberField
              label="衰减"
              value={form.decay}
              min={0}
              step={1}
              help={helpContent('decay')}
              onChange={(value) => onUpdate('decay', value)}
            />
            {datasetChoices.length ? (
              <SelectField
                label="数据集"
                value={form.dataset}
                options={datasetChoices}
                placeholder="自动选择"
                onChange={(value) => onUpdate('dataset', value)}
              />
            ) : (
              <TextField
                label="数据集"
                value={form.dataset}
                maxLength={MAX_CONFIG_TEXT_LENGTH}
                onChange={(value) => onUpdate('dataset', sanitizeConfigText(value))}
              />
            )}
            <SelectField
              label="Alpha 类型"
              value={form.alphaType}
              options={optionValues(options, 'type', form.alphaType, DEFAULT_ALPHA_TYPE_OPTIONS)}
              onChange={(value) => onUpdate('alphaType', value)}
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
              options={optionValues(
                options,
                'neutralization',
                form.neutralization,
                DEFAULT_NEUTRALIZATION_OPTIONS
              )}
              help={helpContent('neutralization')}
              onChange={(value) => onUpdate('neutralization', value)}
            />
            <SelectField
              label="数据净化"
              value={form.pasteurization}
              options={optionValues(
                options,
                'pasteurization',
                form.pasteurization,
                DEFAULT_PASTEURIZATION_OPTIONS
              )}
              help={helpContent('pasteurization')}
              onChange={(value) => onUpdate('pasteurization', value)}
            />
            <SelectField
              label="单位处理"
              value={form.unitHandling}
              options={optionValues(
                options,
                'unitHandling',
                form.unitHandling,
                DEFAULT_UNIT_HANDLING_OPTIONS
              )}
              help={helpContent('unitHandling')}
              onChange={(value) => onUpdate('unitHandling', value)}
            />
            <SelectField
              label="空值处理"
              value={form.nanHandling}
              options={optionValues(
                options,
                'nanHandling',
                form.nanHandling,
                DEFAULT_NAN_HANDLING_OPTIONS
              )}
              help={helpContent('nanHandling')}
              onChange={(value) => onUpdate('nanHandling', value)}
            />
            <SelectField
              label="语言"
              value={form.language}
              options={optionValues(options, 'language', form.language, DEFAULT_LANGUAGE_OPTIONS)}
              onChange={(value) => onUpdate('language', value)}
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
          onChange={(value) => onUpdate('candidates', value)}
        />
        <NumberField
          label="最大轮次"
          value={form.cycles}
          min={1}
          max={10000}
          step={1}
          debounceMs={300}
          onChange={(value) => onUpdate('cycles', value)}
        />
        <NumberField
          label="候选池大小"
          value={form.poolSize}
          min={1}
          max={5000}
          step={1}
          debounceMs={300}
          onChange={(value) => onUpdate('poolSize', value)}
        />
        <NumberField
          label="回测批处理大小"
          value={form.backtestBatchSize}
          min={1}
          max={100}
          step={1}
          debounceMs={300}
          onChange={(value) => onUpdate('backtestBatchSize', value)}
        />
        <div>
          <CheckboxField
            label="每次运行前强制云端同步"
            checked={form.requireCloudSync}
            onChange={(value) => onUpdate('requireCloudSync', value)}
          />
          <p className="mt-1 text-xs leading-5 text-text-tertiary">
            默认关闭：首次无缓存时自动同步，之后直接使用本地缓存；开启后，每次生产运行前都会重新拉取云端
            Alpha 与官方能力集。
          </p>
        </div>
      </ConfigSection>
    </>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// AdvancedConfigGroup — pre-submission quality thresholds
// ──────────────────────────────────────────────────────────────────────────

interface AdvancedConfigGroupProps {
  form: ConfigForm;
  onUpdate: <K extends keyof ConfigForm>(key: K, value: ConfigForm[K]) => void;
}

export function AdvancedConfigGroup({ form, onUpdate }: AdvancedConfigGroupProps) {
  return (
    <ConfigSection
      title="质量阈值"
      description="提交前门禁，低于阈值的候选只能进入研究或优化状态。"
    >
      <NumberField
        label="最低夏普比率"
        value={form.minSharpe}
        min={0}
        step={0.01}
        help={helpContent('minSharpe')}
        debounceMs={300}
        onChange={(value) => onUpdate('minSharpe', value)}
      />
      <NumberField
        label="最低适应度"
        value={form.minFitness}
        min={0}
        step={0.01}
        help={helpContent('minFitness')}
        debounceMs={300}
        onChange={(value) => onUpdate('minFitness', value)}
      />
      <NumberField
        label="最低换手率"
        value={form.minTurnover}
        min={0}
        max={1}
        step={0.01}
        debounceMs={300}
        onChange={(value) => onUpdate('minTurnover', value)}
      />
      <NumberField
        label="最高换手率"
        value={form.platformMaxTurnover}
        min={0}
        max={1}
        step={0.01}
        debounceMs={300}
        onChange={(value) => onUpdate('platformMaxTurnover', value)}
      />
      <NumberField
        label="最大自相关性"
        value={form.maxSelfCorrelation}
        min={0}
        max={1}
        step={0.01}
        help={helpContent('maxSelfCorrelation')}
        debounceMs={300}
        onChange={(value) => onUpdate('maxSelfCorrelation', value)}
      />
      <NumberField
        label="最大权重集中度"
        value={form.maxWeightConcentration}
        min={0}
        max={1}
        step={0.01}
        debounceMs={300}
        onChange={(value) => onUpdate('maxWeightConcentration', value)}
      />
    </ConfigSection>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// ScoringConfigGroup — read-only scoring layer weights + theme toggle
// ──────────────────────────────────────────────────────────────────────────

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

export function ScoringConfigGroup({
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

// ──────────────────────────────────────────────────────────────────────────
// RunConfigSection — composes Basic + Advanced + Scoring + ScoringWeightModal
// ──────────────────────────────────────────────────────────────────────────

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

export function RunConfigSection({
  form,
  schema,
  datasetChoices,
  scoring,
  showWeightModal,
  onUpdate,
  onShowWeightModal,
}: RunConfigSectionProps) {
  return (
    <>
      <BasicConfigGroup
        form={form}
        schema={schema}
        datasetChoices={datasetChoices}
        onUpdate={onUpdate}
      />
      <AdvancedConfigGroup form={form} onUpdate={onUpdate} />
      <ScoringConfigGroup scoring={scoring} onShowWeightModal={onShowWeightModal} />

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
