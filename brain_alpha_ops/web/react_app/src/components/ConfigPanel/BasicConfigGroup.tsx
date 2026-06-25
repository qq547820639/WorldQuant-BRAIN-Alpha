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
} from "./ConfigFormFields";
import { helpContent } from "./fieldHelp";

interface BasicConfigGroupProps {
  form: ConfigForm;
  schema: ConfigSchema | undefined;
  datasetChoices: Array<{ value: string; label: string }>;
  onUpdate: <K extends keyof ConfigForm>(key: K, value: ConfigForm[K]) => void;
}

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

export default function BasicConfigGroup({
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
    </>
  );
}
