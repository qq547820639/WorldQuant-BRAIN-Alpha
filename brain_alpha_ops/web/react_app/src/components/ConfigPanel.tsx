/** Editable configuration panel for the next research run. */

import { useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { useApi } from "@/hooks/useApi";
import type { BrainCredentials, RunConfig } from "@/types";
import ProgressFeedback from "@/components/ProgressFeedback";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  credentials: BrainCredentials;
  onCredentialsChange: (credentials: BrainCredentials) => void;
}

interface ConfigResponse {
  ok: boolean;
  config?: RunConfig;
}

interface DatasetOption {
  id: string;
  name?: string;
  field_count?: number;
  category?: string;
  label?: string;
}

interface ConfigSchema {
  settings_options?: Record<string, Array<string | number>>;
  dataset_options?: DatasetOption[];
}

interface ConfigSchemaResponse {
  ok: boolean;
  schema?: ConfigSchema;
}

interface ConnectionTestResponse {
  ok: boolean;
  environment?: string;
  auth?: string;
  error?: string;
  error_code?: string;
}

interface ConfigForm {
  environment: string;
  autoSubmit: boolean;
  instrumentType: string;
  region: string;
  universe: string;
  delay: number;
  decay: number;
  neutralization: string;
  dataset: string;
  pasteurization: string;
  unitHandling: string;
  nanHandling: string;
  language: string;
  alphaType: string;
  candidates: number;
  cycles: number;
  poolSize: number;
  backtestBatchSize: number;
  requireCloudSync: boolean;
  minSharpe: number;
  minFitness: number;
  minTurnover: number;
  platformMaxTurnover: number;
  maxSelfCorrelation: number;
  maxWeightConcentration: number;
}

const MAX_CONFIG_TEXT_LENGTH = 128;
const CONFIG_TEXT_PATTERN = /^[A-Za-z0-9_.:-]*$/;
const DEFAULT_REGION_OPTIONS = ["USA", "CHN", "EUR", "GLB"];
const DEFAULT_UNIVERSE_OPTIONS = ["TOP3000", "TOP1000", "TOP500"];
const DEFAULT_DELAY_OPTIONS = ["0", "1"];
const DEFAULT_NEUTRALIZATION_OPTIONS = ["SUBINDUSTRY", "INDUSTRY", "SECTOR", "MARKET", "NONE"];
const DEFAULT_INSTRUMENT_TYPE_OPTIONS = ["EQUITY"];
const DEFAULT_PASTEURIZATION_OPTIONS = ["ON", "OFF"];
const DEFAULT_UNIT_HANDLING_OPTIONS = ["VERIFY", "RAW", "NONE"];
const DEFAULT_NAN_HANDLING_OPTIONS = ["ON", "OFF"];
const DEFAULT_LANGUAGE_OPTIONS = ["FASTEXPR"];
const DEFAULT_ALPHA_TYPE_OPTIONS = ["REGULAR", "POWER_POOL", "ATOM", "PYRAMID"];

type SelectOption = string | { value: string; label: string };

export default function ConfigPanel({ notify, credentials, onCredentialsChange }: Props) {
  const configApi = useApi<ConfigResponse>();
  const schemaApi = useApi<ConfigSchemaResponse>();
  const saveApi = useApi<ConfigResponse>();
  const connectionApi = useApi<ConnectionTestResponse>();
  const [form, setForm] = useState<ConfigForm | null>(null);
  const [initialForm, setInitialForm] = useState<ConfigForm | null>(null);
  const importInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    void configApi.call("/api/config");
    void schemaApi.call("/api/config_schema");
  }, [configApi.call, schemaApi.call]);

  const config = useMemo(() => configApi.data?.config ?? null, [configApi.data]);
  const schema = schemaApi.data?.schema;

  useEffect(() => {
    if (!config) return;
    const next = formFromConfig(config);
    setForm(next);
    setInitialForm(next);
  }, [config]);

  const dirty = useMemo(
    () => Boolean(form && initialForm && JSON.stringify(form) !== JSON.stringify(initialForm)),
    [form, initialForm],
  );
  const validationError = form ? validateForm(form, schema) : "";

  const update = <K extends keyof ConfigForm>(key: K, value: ConfigForm[K]) => {
    setForm((current) => current ? { ...current, [key]: value } : current);
  };

  const updateCredential = <K extends keyof BrainCredentials>(key: K, value: BrainCredentials[K]) => {
    onCredentialsChange({ ...credentials, [key]: value });
  };

  const reload = () => {
    void configApi.call("/api/config");
    void schemaApi.call("/api/config_schema");
  };

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form || validationError) {
      notify("warning", validationError || "配置尚未准备好保存");
      return;
    }
    const result = await saveApi.call("/api/config", {
      method: "POST",
      body: JSON.stringify(payloadFromForm(form)),
    });
    if (!result?.ok) {
      notify("error", result?.error || "保存配置失败");
      return;
    }
    notify("success", "配置已保存");
    void configApi.call("/api/config");
  };

  const exportConfig = () => {
    if (!form) return;
    const blob = new Blob([JSON.stringify(payloadFromForm(form), null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `brain-alpha-config-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(url);
    notify("success", "配置已导出");
  };

  const importConfig = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (!file || !form) return;
    try {
      const imported = formFromImport(JSON.parse(await file.text()), form);
      const error = validateForm(imported, schema);
      if (error) {
        notify("error", error);
        return;
      }
      setForm(imported);
      notify("success", "配置已导入");
    } catch (error) {
      notify("error", error instanceof Error ? error.message : "无效的配置JSON");
    }
  };

  const testConnection = async () => {
    if (!form || validationError) {
      notify("warning", validationError || "配置尚未准备好测试连接");
      return;
    }
    const result = await connectionApi.call("/api/test_connection", {
      method: "POST",
      body: JSON.stringify(payloadFromForm(form, credentials)),
    });
    if (!result?.ok) {
      notify("error", result?.error || "BRAIN 连接测试失败");
      return;
    }
    notify("success", "BRAIN 连接测试通过");
  };

  if (configApi.loading && !config) {
    return (
      <ProgressFeedback
        state="loading"
        title="配置"
        progress={{ phase: "config_load", status_message: "正在加载配置。" }}
      />
    );
  }

  if (configApi.error && !config) {
    return (
      <div className="card">
        <p className="text-danger text-sm">加载配置失败: {configApi.error}</p>
        <button type="button" onClick={reload} className="btn-secondary text-sm mt-3">重试</button>
      </div>
    );
  }

  if (!form) return null;

  const options = schema?.settings_options;
  const datasetChoices = datasetSelectOptions(schema, form.dataset);
  const scoring = config?.ops?.scoring ?? config?.scoring;
  const hasSessionCredentials = Boolean(credentials.username || credentials.password || credentials.token);

  return (
    <form onSubmit={save} className="w-full max-w-5xl min-w-0 space-y-5 animate-fade-in">
      <div className="reader-panel flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 max-w-2xl">
          <h2 className="text-xl font-semibold text-slate-950">连接与生产参数</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            先填写 BRAIN 会话凭证并测试连接，再调整本次运行参数。保存配置不会保存账号、密码或 token。
          </p>
        </div>
        <div className="flex w-full flex-wrap justify-end gap-2 sm:w-auto">
          <input
            ref={importInputRef}
            type="file"
            accept="application/json,.json"
            className="hidden"
            aria-label="导入配置JSON"
            onChange={importConfig}
          />
          <button
            type="button"
            onClick={() => importInputRef.current?.click()}
            className="btn-secondary text-sm"
            disabled={saveApi.loading}
          >
            导入
          </button>
          <button
            type="button"
            onClick={exportConfig}
            className="btn-secondary text-sm"
            disabled={saveApi.loading}
          >
            导出
          </button>
          <button
            type="button"
            onClick={() => initialForm && setForm({ ...initialForm })}
            className="btn-secondary text-sm disabled:opacity-50"
            disabled={!dirty || saveApi.loading}
          >
            重置
          </button>
          <button
            type="submit"
            className="btn-primary text-sm"
            disabled={!dirty || Boolean(validationError) || saveApi.loading}
          >
            {saveApi.loading ? "保存中..." : "保存"}
          </button>
        </div>
      </div>

      {validationError && <p role="alert" className="text-xs text-danger">{validationError}</p>}
      {saveApi.error && <p role="alert" className="text-xs text-danger">{saveApi.error}</p>}

      <ConfigSection
        title="BRAIN 连接"
        description="这些字段只保留在当前浏览器内存里，用于连接测试和本次流水线请求。"
      >
        <TextField
          label="账户邮箱"
          value={credentials.username}
          autoComplete="username"
          inputMode="email"
          maxLength={160}
          onChange={(value) => updateCredential("username", value.trim())}
        />
        <PasswordField
          label="密码"
          value={credentials.password}
          onChange={(value) => updateCredential("password", value)}
        />
        <TextField
          label="Token"
          value={credentials.token}
          autoComplete="off"
          maxLength={512}
          onChange={(value) => updateCredential("token", value.trim())}
        />
        <div className="flex flex-col gap-2 sm:items-start">
          <button
            type="button"
            onClick={testConnection}
            className="btn-secondary text-sm"
            disabled={connectionApi.loading || Boolean(validationError)}
          >
            {connectionApi.loading ? "测试中..." : "测试 BRAIN 连接"}
          </button>
          <p className={`text-xs ${connectionApi.error ? "text-danger" : connectionApi.data?.ok ? "text-success" : "text-muted"}`} role="status" aria-live="polite">
            {connectionApi.error
              ? `连接失败: ${connectionApi.error}`
              : connectionApi.data?.ok
                ? `连接正常: ${connectionApi.data.environment || form.environment}`
                : hasSessionCredentials
                  ? "凭证已填写，尚未测试"
                  : "未填写则使用服务端环境变量"}
          </p>
        </div>
      </ConfigSection>

      <ConfigSection title="BRAIN 设置" description="字段和选项来自后端公开的官方能力集校验，不在前端自定义扩展。">
        <SelectField label="资产类型" value={form.instrumentType} options={optionValues(options, "instrumentType", form.instrumentType, DEFAULT_INSTRUMENT_TYPE_OPTIONS)} onChange={(value) => update("instrumentType", value)} />
        <SelectField label="区域" value={form.region} options={optionValues(options, "region", form.region, DEFAULT_REGION_OPTIONS)} onChange={(value) => update("region", value)} />
        <SelectField label="股票池" value={form.universe} options={optionValues(options, "universe", form.universe, DEFAULT_UNIVERSE_OPTIONS)} onChange={(value) => update("universe", value)} />
        <SelectField label="延迟" value={String(form.delay)} options={optionValues(options, "delay", String(form.delay), DEFAULT_DELAY_OPTIONS)} onChange={(value) => update("delay", Number(value))} />
        <NumberField label="衰减" value={form.decay} min={0} step={1} onChange={(value) => update("decay", value)} />
        <SelectField label="中性化" value={form.neutralization} options={optionValues(options, "neutralization", form.neutralization, DEFAULT_NEUTRALIZATION_OPTIONS)} onChange={(value) => update("neutralization", value)} />
        {datasetChoices.length ? (
          <SelectField
            label="数据集"
            value={form.dataset}
            options={datasetChoices}
            placeholder="自动选择"
            onChange={(value) => update("dataset", value)}
          />
        ) : (
          <TextField
            label="数据集"
            value={form.dataset}
            maxLength={MAX_CONFIG_TEXT_LENGTH}
            onChange={(value) => update("dataset", sanitizeConfigText(value))}
          />
        )}
        <SelectField label="Alpha 类型" value={form.alphaType} options={optionValues(options, "type", form.alphaType, DEFAULT_ALPHA_TYPE_OPTIONS)} onChange={(value) => update("alphaType", value)} />
        <SelectField label="数据净化" value={form.pasteurization} options={optionValues(options, "pasteurization", form.pasteurization, DEFAULT_PASTEURIZATION_OPTIONS)} onChange={(value) => update("pasteurization", value)} />
        <SelectField label="单位处理" value={form.unitHandling} options={optionValues(options, "unitHandling", form.unitHandling, DEFAULT_UNIT_HANDLING_OPTIONS)} onChange={(value) => update("unitHandling", value)} />
        <SelectField label="空值处理" value={form.nanHandling} options={optionValues(options, "nanHandling", form.nanHandling, DEFAULT_NAN_HANDLING_OPTIONS)} onChange={(value) => update("nanHandling", value)} />
        <SelectField label="语言" value={form.language} options={optionValues(options, "language", form.language, DEFAULT_LANGUAGE_OPTIONS)} onChange={(value) => update("language", value)} />
      </ConfigSection>

      <ConfigSection title="预算控制" description="用于限制单次生产运行的候选数量、轮次和回测批量。">
        <NumberField label="每轮最大候选数" value={form.candidates} min={1} max={1000} step={1} onChange={(value) => update("candidates", value)} />
        <NumberField label="最大轮次" value={form.cycles} min={1} max={10000} step={1} onChange={(value) => update("cycles", value)} />
        <NumberField label="候选池大小" value={form.poolSize} min={1} max={5000} step={1} onChange={(value) => update("poolSize", value)} />
        <NumberField label="回测批处理大小" value={form.backtestBatchSize} min={1} max={100} step={1} onChange={(value) => update("backtestBatchSize", value)} />
        <CheckboxField label="需要云端同步" checked={form.requireCloudSync} onChange={(value) => update("requireCloudSync", value)} />
      </ConfigSection>

      <ConfigSection title="质量阈值" description="提交前门禁，低于阈值的候选只能进入研究或优化状态。">
        <NumberField label="最低夏普比率" value={form.minSharpe} min={0} step={0.01} onChange={(value) => update("minSharpe", value)} />
        <NumberField label="最低适应度" value={form.minFitness} min={0} step={0.01} onChange={(value) => update("minFitness", value)} />
        <NumberField label="最低换手率" value={form.minTurnover} min={0} max={1} step={0.01} onChange={(value) => update("minTurnover", value)} />
        <NumberField label="最高换手率" value={form.platformMaxTurnover} min={0} max={1} step={0.01} onChange={(value) => update("platformMaxTurnover", value)} />
        <NumberField label="最大自相关性" value={form.maxSelfCorrelation} min={0} max={1} step={0.01} onChange={(value) => update("maxSelfCorrelation", value)} />
        <NumberField label="最大权重集中度" value={form.maxWeightConcentration} min={0} max={1} step={0.01} onChange={(value) => update("maxWeightConcentration", value)} />
      </ConfigSection>

      <ConfigSection title="评分配置" description="当前评分层权重为只读展示，避免和官方门禁配置混淆。">
        <ConfigValue label="先验权重" value={scoring?.prior_layer_weight} />
        <ConfigValue label="经验权重" value={scoring?.empirical_layer_weight} />
        <ConfigValue label="检查清单权重" value={scoring?.checklist_layer_weight} />
        <ConfigValue label="市场状态" value={scoring?.market_regime} />
      </ConfigSection>

      <ConfigSection title="环境设置" description="Web 控制台只允许保存非提交运行配置；真实提交必须走单独的人工确认流程。">
        <ConfigValue label="自动提交" value="关闭（Web 保存强制）" />
      </ConfigSection>
    </form>
  );
}

function formFromConfig(config: RunConfig): ConfigForm {
  const settings = config.ops?.settings ?? config.settings;
  const budget = config.ops?.budget ?? config.budget;
  const thresholds = config.ops?.thresholds ?? config.thresholds;
  return {
    environment: config.environment || "production",
    autoSubmit: false,
    instrumentType: String(settings?.instrumentType || "EQUITY"),
    region: String(settings?.region || "USA"),
    universe: String(settings?.universe || "TOP3000"),
    delay: Number(settings?.delay ?? 1),
    decay: Number(settings?.decay ?? 10),
    neutralization: String(settings?.neutralization || "SUBINDUSTRY"),
    dataset: String(settings?.dataset || ""),
    pasteurization: String(settings?.pasteurization || "ON"),
    unitHandling: String(settings?.unitHandling || "VERIFY"),
    nanHandling: String(settings?.nanHandling || "ON"),
    language: String(settings?.language || "FASTEXPR"),
    alphaType: String(settings?.type || "REGULAR"),
    candidates: Number(budget?.max_candidates_per_cycle ?? 20),
    cycles: Number(budget?.max_cycles ?? 10),
    poolSize: Number(budget?.retained_alpha_pool_size ?? 10),
    backtestBatchSize: Number(budget?.official_backtest_batch_size ?? 3),
    requireCloudSync: Boolean(budget?.require_cloud_sync),
    minSharpe: Number(thresholds?.min_sharpe ?? 1.25),
    minFitness: Number(thresholds?.min_fitness ?? 1),
    minTurnover: Number(thresholds?.min_turnover ?? 0.01),
    platformMaxTurnover: Number(thresholds?.platform_max_turnover ?? 0.7),
    maxSelfCorrelation: Number(thresholds?.max_self_correlation ?? 0.7),
    maxWeightConcentration: Number(thresholds?.max_weight_concentration ?? 0.1),
  };
}

function payloadFromForm(form: ConfigForm, credentials?: BrainCredentials) {
  const payload: Record<string, unknown> = {
    environment: form.environment,
    autoSubmit: false,
    settings: {
      instrumentType: form.instrumentType,
      region: form.region,
      universe: form.universe,
      delay: form.delay,
      decay: form.decay,
      neutralization: form.neutralization,
      dataset: form.dataset,
      pasteurization: form.pasteurization,
      unitHandling: form.unitHandling,
      nanHandling: form.nanHandling,
      language: form.language,
      type: form.alphaType,
    },
    candidates: form.candidates,
    cycles: form.cycles,
    poolSize: form.poolSize,
    backtestBatchSize: form.backtestBatchSize,
    requireCloudSync: form.requireCloudSync,
    minSharpe: form.minSharpe,
    minFitness: form.minFitness,
    minTurnover: form.minTurnover,
    platformMaxTurnover: form.platformMaxTurnover,
    maxSelfCorrelation: form.maxSelfCorrelation,
    maxWeightConcentration: form.maxWeightConcentration,
  };
  const username = credentials?.username.trim() || "";
  const password = credentials?.password || "";
  const token = credentials?.token.trim() || "";
  if (username) payload.username = username;
  if (password) payload.password = password;
  if (token) payload.token = token;
  return payload;
}

function formFromImport(value: unknown, fallback: ConfigForm): ConfigForm {
  const root = asRecord(value);
  if (!root) throw new Error("配置JSON必须是一个对象。");
  const source = asRecord(root.config) || root;
  if (asRecord(source.ops)) {
    return formFromConfig(source as unknown as RunConfig);
  }
  const settings = asRecord(source.settings) || {};
  return {
    ...fallback,
    environment: stringValue(source.environment, fallback.environment),
    autoSubmit: false,
    instrumentType: stringValue(settings.instrumentType, fallback.instrumentType),
    region: stringValue(settings.region, fallback.region),
    universe: stringValue(settings.universe, fallback.universe),
    delay: numberValue(settings.delay, fallback.delay),
    decay: numberValue(settings.decay, fallback.decay),
    neutralization: stringValue(settings.neutralization, fallback.neutralization),
    dataset: stringValue(settings.dataset, fallback.dataset),
    pasteurization: stringValue(settings.pasteurization, fallback.pasteurization),
    unitHandling: stringValue(settings.unitHandling, fallback.unitHandling),
    nanHandling: stringValue(settings.nanHandling, fallback.nanHandling),
    language: stringValue(settings.language, fallback.language),
    alphaType: stringValue(settings.type ?? settings.alphaType, fallback.alphaType),
    candidates: numberValue(source.candidates, fallback.candidates),
    cycles: numberValue(source.cycles, fallback.cycles),
    poolSize: numberValue(source.poolSize, fallback.poolSize),
    backtestBatchSize: numberValue(source.backtestBatchSize, fallback.backtestBatchSize),
    requireCloudSync: booleanValue(source.requireCloudSync, fallback.requireCloudSync),
    minSharpe: numberValue(source.minSharpe, fallback.minSharpe),
    minFitness: numberValue(source.minFitness, fallback.minFitness),
    minTurnover: numberValue(source.minTurnover, fallback.minTurnover),
    platformMaxTurnover: numberValue(source.platformMaxTurnover, fallback.platformMaxTurnover),
    maxSelfCorrelation: numberValue(source.maxSelfCorrelation, fallback.maxSelfCorrelation),
    maxWeightConcentration: numberValue(source.maxWeightConcentration, fallback.maxWeightConcentration),
  };
}

function validateForm(form: ConfigForm, schema?: ConfigSchema) {
  const options = schema?.settings_options;
  if (!form.instrumentType || !form.region || !form.universe || !form.neutralization || !form.alphaType) {
    return "BRAIN 设置不完整。";
  }
  if (!isAllowedOption(form.instrumentType, options, "instrumentType", DEFAULT_INSTRUMENT_TYPE_OPTIONS)) {
    return "不支持的资产类型。";
  }
  if (!isAllowedOption(form.region, options, "region", DEFAULT_REGION_OPTIONS)) return "不支持的区域。";
  if (!isAllowedOption(form.universe, options, "universe", DEFAULT_UNIVERSE_OPTIONS)) return "不支持的股票池。";
  if (!isAllowedOption(form.neutralization, options, "neutralization", DEFAULT_NEUTRALIZATION_OPTIONS)) {
    return "不支持的中性化方式。";
  }
  if (!isAllowedOption(form.alphaType, options, "type", DEFAULT_ALPHA_TYPE_OPTIONS)) {
    return "不支持的 Alpha 类型。";
  }
  if (!isAllowedOption(form.pasteurization, options, "pasteurization", DEFAULT_PASTEURIZATION_OPTIONS)) {
    return "不支持的数据净化方式。";
  }
  if (!isAllowedOption(form.unitHandling, options, "unitHandling", DEFAULT_UNIT_HANDLING_OPTIONS)) {
    return "不支持的单位处理方式。";
  }
  if (!isAllowedOption(form.nanHandling, options, "nanHandling", DEFAULT_NAN_HANDLING_OPTIONS)) {
    return "不支持的空值处理方式。";
  }
  if (!isAllowedOption(form.language, options, "language", DEFAULT_LANGUAGE_OPTIONS)) {
    return "不支持的表达式语言。";
  }
  if (form.dataset.length > MAX_CONFIG_TEXT_LENGTH) return `数据集长度不能超过 ${MAX_CONFIG_TEXT_LENGTH} 个字符。`;
  if (form.dataset && !CONFIG_TEXT_PATTERN.test(form.dataset)) {
    return "数据集只能包含字母、数字、下划线、短横线、点或冒号。";
  }
  const datasetValues = datasetAllowedValues(schema);
  if (form.dataset && datasetValues.length && !datasetValues.includes(form.dataset)) {
    return "不支持的数据集，请从下拉列表选择。";
  }
  if (!isIntegerInRange(form.delay, 0, 1)) return "延迟必须为 0 或 1。";
  if (!isIntegerInRange(form.decay, 0)) return "衰减必须为非负整数。";
  if (!isIntegerInRange(form.candidates, 1, 1000)) return "每轮最大候选数必须在 1 到 1000 之间。";
  if (!isIntegerInRange(form.cycles, 1, 10000)) return "最大轮次必须在 1 到 10000 之间。";
  if (!isIntegerInRange(form.poolSize, 1, 5000)) return "候选池大小必须在 1 到 5000 之间。";
  if (!isIntegerInRange(form.backtestBatchSize, 1, 100)) return "回测批处理大小必须在 1 到 100 之间。";
  for (const [label, value] of [
    ["最低夏普比率", form.minSharpe],
    ["最低适应度", form.minFitness],
  ] as const) {
    if (!Number.isFinite(value) || value < 0) return `${label} 必须为非负数。`;
  }
  for (const [label, value] of [
    ["最低换手率", form.minTurnover],
    ["最高换手率", form.platformMaxTurnover],
    ["最大自相关性", form.maxSelfCorrelation],
    ["最大权重集中度", form.maxWeightConcentration],
  ] as const) {
    if (!Number.isFinite(value) || value < 0 || value > 1) return `${label} 必须在 0 到 1 之间。`;
  }
  if (form.minTurnover > form.platformMaxTurnover) return "最低换手率不能超过最高换手率。";
  return "";
}

function optionValues(
  options: Record<string, Array<string | number>> | undefined,
  key: string,
  current: string,
  fallback: string[] = [],
) {
  const values = options?.[key]?.map(String).filter(Boolean) || fallback;
  return Array.from(new Set([...values, current].filter(Boolean)));
}

function datasetSelectOptions(schema: ConfigSchema | undefined, current: string): SelectOption[] {
  const seen = new Set<string>();
  const rows = schema?.dataset_options || [];
  const choices: SelectOption[] = [];
  for (const row of rows) {
    const value = String(row.id || "").trim();
    if (!value || seen.has(value)) continue;
    choices.push({ value, label: datasetOptionLabel(row, value) });
    seen.add(value);
  }
  for (const value of schema?.settings_options?.dataset?.map(String).filter(Boolean) || []) {
    if (seen.has(value)) continue;
    choices.push({ value, label: value });
    seen.add(value);
  }
  if (current && !seen.has(current)) {
    choices.unshift({ value: current, label: `当前值 - ${current}` });
  }
  return choices;
}

function datasetAllowedValues(schema: ConfigSchema | undefined) {
  return datasetSelectOptions(schema, "").map((option) => typeof option === "string" ? option : option.value);
}

function datasetOptionLabel(row: DatasetOption, fallback: string) {
  if (row.label) return row.label;
  const name = row.name ? ` - ${row.name}` : "";
  const fieldCount = Number(row.field_count || 0);
  const count = Number.isFinite(fieldCount) && fieldCount > 0 ? `, ${fieldCount} fields` : "";
  return `${fallback}${name}${count}`;
}

function allowedOptionValues(
  options: Record<string, Array<string | number>> | undefined,
  key: string,
  fallback: string[],
) {
  const values = options?.[key]?.map(String).filter(Boolean);
  return values?.length ? values : fallback;
}

function isAllowedOption(
  value: string,
  options: Record<string, Array<string | number>> | undefined,
  key: string,
  fallback: string[],
) {
  return allowedOptionValues(options, key, fallback).includes(value);
}

function isIntegerInRange(value: number, min: number, max = Number.POSITIVE_INFINITY) {
  return Number.isInteger(value) && value >= min && value <= max;
}

function parseNumber(value: string) {
  return value.trim() ? Number(value) : Number.NaN;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function stringValue(value: unknown, fallback: string) {
  return typeof value === "string" ? value : fallback;
}

function numberValue(value: unknown, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function booleanValue(value: unknown, fallback: boolean) {
  return typeof value === "boolean" ? value : fallback;
}

function sanitizeConfigText(value: string) {
  return value.replace(/[\x00-\x1F\x7F]/g, "").slice(0, MAX_CONFIG_TEXT_LENGTH);
}

function ConfigSection({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <fieldset className="reader-panel min-w-0">
      <legend className="px-1 text-base font-semibold text-slate-950">{title}</legend>
      {description ? <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{description}</p> : null}
      <div className="mt-4 grid grid-cols-1 gap-x-5 gap-y-4 md:grid-cols-2">{children}</div>
    </fieldset>
  );
}

function TextField({
  label,
  value,
  maxLength,
  autoComplete,
  inputMode,
  onChange,
}: {
  label: string;
  value: string;
  maxLength?: number;
  autoComplete?: string;
  inputMode?: "email" | "text";
  onChange: (value: string) => void;
}) {
  return (
    <label className="form-label">
      <span className="block mb-1">{label}</span>
      <input
        type="text"
        value={value}
        maxLength={maxLength}
        autoComplete={autoComplete}
        inputMode={inputMode}
        onChange={(event) => onChange(event.currentTarget.value)}
        className={inputClass}
      />
    </label>
  );
}

function PasswordField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="form-label">
      <span className="mb-1 block">{label}</span>
      <input
        type="password"
        value={value}
        autoComplete="current-password"
        onChange={(event) => onChange(event.currentTarget.value)}
        className={inputClass}
      />
    </label>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="form-label">
      <span className="block mb-1">{label}</span>
      <input
        type="number"
        value={Number.isFinite(value) ? value : ""}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange(parseNumber(event.currentTarget.value))}
        className={inputClass}
      />
    </label>
  );
}

function normalizeSelectOptions(options: SelectOption[]) {
  return options.map((option) => typeof option === "string" ? { value: option, label: option } : option);
}

function SelectField({
  label,
  value,
  options,
  placeholder,
  onChange,
}: {
  label: string;
  value: string;
  options: SelectOption[];
  placeholder?: string;
  onChange: (value: string) => void;
}) {
  const choices = normalizeSelectOptions(options);
  return (
    <label className="form-label">
      <span className="block mb-1">{label}</span>
      <select value={value} onChange={(event) => onChange(event.currentTarget.value)} className={inputClass}>
        {placeholder ? <option value="">{placeholder}</option> : null}
        {choices.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  );
}

function CheckboxField({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="flex items-center justify-between gap-3 border-b border-slate-200 py-2 text-sm font-medium text-slate-700">
      <span>{label}</span>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.currentTarget.checked)} className="h-4 w-4 accent-brand-500" />
    </label>
  );
}

function ConfigValue({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="flex min-w-0 flex-wrap justify-between gap-x-3 gap-y-1 border-b border-slate-200 py-1.5 text-sm">
      <span className="text-slate-600">{label}</span>
      <span className="min-w-0 break-all font-mono text-slate-900">{String(value ?? "-")}</span>
    </div>
  );
}

const inputClass = "form-input";
