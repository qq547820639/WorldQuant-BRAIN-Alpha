/** Editable configuration panel for the next research run. */

import { useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { apiErrorMessage, safeDisplayErrorMessage, type ApiErrorExperiencePayload } from "@/helpers/errorExperience";
import { useApi } from "@/hooks/useApi";
import { useGlobalData } from "@/hooks/useGlobalData";
import type { BrainCredentials, RunConfig } from "@/types";
import ProgressFeedback from "@/components/ProgressFeedback";
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
  datasetSelectOptions,
  payloadFromForm,
  formFromConfig,
  formFromImport,
  validateForm,
  credentialsPayload,
} from "./ConfigPanel/utils";
import { ConfigSection, TextField, PasswordField, NumberField, SelectField, CheckboxField, ConfigValue } from "./ConfigPanel/ConfigFormFields";
import ScoringWeightModal from "./ConfigPanel/ScoringWeightModal";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  credentials: BrainCredentials;
  onCredentialsChange: (credentials: BrainCredentials) => void;
  onConnectionTested?: (success: boolean, error: string | null) => void;
  connected?: boolean;
  contextFresh?: boolean;
  managedCredentialsAvailable?: boolean;
  onLoggedOut?: () => void;
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


interface ConfigSchemaResponse {
  ok: boolean;
  schema?: ConfigSchema;
}

interface ConnectionTestResponse extends ApiErrorExperiencePayload {
  ok: boolean;
  environment?: string;
  auth?: string;
  error?: string;
  error_code?: string;
}

export default function ConfigPanel({
  notify,
  credentials,
  onCredentialsChange,
  onConnectionTested,
  connected = false,
  contextFresh = false,
  managedCredentialsAvailable = false,
  onLoggedOut,
}: Props) {
  const { config: globalConfig, refreshAll } = useGlobalData();
  const schemaApi = useApi<ConfigSchemaResponse>();
  const saveApi = useApi<ConfigResponse>();
  const connectionApi = useApi<ConnectionTestResponse>();
  const logoutApi = useApi<{ ok: boolean; error?: string; error_code?: string }>();
  const [form, setForm] = useState<ConfigForm | null>(null);
  const [initialForm, setInitialForm] = useState<ConfigForm | null>(null);
  const [temporaryConnectionOpen, setTemporaryConnectionOpen] = useState(false);
  const [showWeightModal, setShowWeightModal] = useState(false); // P2-4
  const importInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    void schemaApi.call("/api/config_schema");
  }, [schemaApi.call]);

  const config = useMemo(() => globalConfig.data?.config ?? null, [globalConfig.data]);
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
  const validationError = form ? validateForm(form, schema) : null;

  const update = <K extends keyof ConfigForm>(key: K, value: ConfigForm[K]) => {
    setForm((current) => current ? { ...current, [key]: value } : current);
  };

  const updateCredential = <K extends keyof BrainCredentials>(key: K, value: BrainCredentials[K]) => {
    onCredentialsChange({ ...credentials, [key]: value });
  };

  const reload = () => {
    refreshAll();
    void schemaApi.call("/api/config_schema");
  };

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form || validationError !== null) {
      notify("warning", validationError || "配置尚未准备好保存");
      return;
    }
    const result = await saveApi.call("/api/config", {
      method: "POST",
      body: JSON.stringify(payloadFromForm(form)),
    });
    if (!result?.ok) {
      notify("error", apiErrorMessage(result, "保存配置失败"));
      return;
    }
    notify("success", "配置已保存");
    refreshAll();
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
      if (error !== null) {
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
    if (!form || validationError !== null) {
      notify("warning", validationError || "配置尚未准备好测试连接");
      return;
    }
    const result = await connectionApi.call("/api/test_connection", {
      method: "POST",
      body: JSON.stringify({ ...payloadFromForm(form), ...credentialsPayload(credentials) }),
    });
    if (!result?.ok) {
      const err = safeDisplayErrorMessage(apiErrorMessage(result, "BRAIN 连接测试失败"));
      notify("error", err);
      onConnectionTested?.(false, err);
      return;
    }
    notify("success", "BRAIN 连接测试通过");
    onConnectionTested?.(true, null);
  };

  const logoutLocalSession = async () => {
    const result = await logoutApi.call("/api/logout", { method: "POST" });
    if (!result?.ok) {
      notify("error", safeDisplayErrorMessage(apiErrorMessage(result, "退出本地会话失败")));
      return;
    }
    onCredentialsChange({ username: "", password: "", token: "" });
    setTemporaryConnectionOpen(false);
    onLoggedOut?.();
    notify("success", "已退出本地会话并清空页面凭证");
  };

  if (globalConfig.loading && !config) {
    return (
      <ProgressFeedback
        state="loading"
        title="配置"
        progress={{ phase: "config_load", status_message: "正在加载配置。" }}
      />
    );
  }

  if (globalConfig.error && !config) {
    return (
      <div className="panel">
        <p className="text-negative text-sm">加载配置失败: {safeDisplayErrorMessage(globalConfig.error)}</p>
        <button type="button" onClick={reload} className="btn btn-secondary btn-sm">重试</button>
      </div>
    );
  }

  if (!form) return null;

  const options = schema?.settings_options;
  const datasetChoices = datasetSelectOptions(schema, form.dataset);
  const scoring = config?.ops?.scoring ?? config?.scoring;
  const hasSessionCredentials = Boolean(credentials.username || credentials.password || credentials.token);
  const cacheOnlyMode = contextFresh && !connected;
  const showCredentialEditor = !cacheOnlyMode || temporaryConnectionOpen;
  const connectionStatusText = connectionApi.error
    ? `连接失败: ${safeDisplayErrorMessage(connectionApi.error)}`
    : connectionApi.data?.ok
      ? `连接正常: ${connectionApi.data.environment || form.environment}`
      : hasSessionCredentials
        ? "凭证已填写，尚未测试"
        : managedCredentialsAvailable
          ? "未填写则使用维护者配置的托管凭证"
          : "请临时填写页面凭证";

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

  const formatHelp = (help: typeof FIELD_HELP[string]) =>
    `${help.what}\n\n推荐: ${help.recommendation}\n⚠️ ${help.risk}`;

  const HelpIcon = ({ help }: { help: typeof FIELD_HELP[string] }) => (
    <span title={formatHelp(help)} className="cursor-help ml-1 text-xs opacity-60 hover:opacity-100" aria-label="帮助" role="tooltip">❓</span>
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

  const helpContent = (key: string) => {
    const entry = FIELD_HELP[key];
    return entry ? <HelpIcon help={entry} /> : null;
  };

  return (
    <form onSubmit={save} className="w-full max-w-5xl min-w-0 space-y-5 animate-fade-in">
      <div className="panel flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 max-w-2xl">
          <h2 className="text-xl font-semibold text-text-primary">连接与生产参数</h2>
          <p className="mt-2 text-sm leading-6 text-text-secondary">
            {cacheOnlyMode
              ? "当前使用本地缓存。需要官方同步、官方回测或提交前复核时，再临时连接官方服务。"
              : "调整本次运行参数；需要官方同步、官方回测或提交前复核时，临时填写 BRAIN 会话凭证并测试连接。保存配置不会保存账号、密码或 token。"}
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
            className="btn btn-secondary btn-sm"
            disabled={saveApi.loading}
          >
            导入
          </button>
          <button
            type="button"
            onClick={exportConfig}
            className="btn btn-secondary btn-sm"
            disabled={saveApi.loading}
          >
            导出
          </button>
          <button
            type="button"
            onClick={() => initialForm && setForm({ ...initialForm })}
            className="btn btn-secondary btn-sm disabled:opacity-50"
            disabled={!dirty || saveApi.loading}
          >
            重置
          </button>
          <button
            type="submit"
            className="btn btn-primary btn-sm"
            disabled={!dirty || validationError !== null || saveApi.loading}
          >
            {saveApi.loading ? "保存中..." : "保存"}
          </button>
        </div>
      </div>

      {validationError !== null && <p role="alert" className="text-xs text-negative">{validationError}</p>}
      {saveApi.error && <p role="alert" className="text-xs text-negative">{safeDisplayErrorMessage(saveApi.error)}</p>}

      {cacheOnlyMode && (
        <LocalCacheConnectionSection
          temporaryConnectionOpen={temporaryConnectionOpen}
          logoutLoading={logoutApi.loading}
          logoutError={logoutApi.error ? safeDisplayErrorMessage(logoutApi.error) : null}
          onOpenTemporaryConnection={() => setTemporaryConnectionOpen(true)}
          onCloseTemporaryConnection={() => setTemporaryConnectionOpen(false)}
          onLogout={logoutLocalSession}
        />
      )}

      {showCredentialEditor && (
        <ConfigSection
          title={cacheOnlyMode ? "临时连接官方服务" : "BRAIN 连接"}
          description={cacheOnlyMode
            ? "这些字段仅用于本次同步、官方回测或提交前复核；折叠后不会保存到配置文件。"
            : "这些字段只保留在当前页面，用于本次连接测试和验证。"}
        >
          <TextField
            label="账户邮箱"
            value={credentials.username}
            autoComplete="off"
            inputMode="email"
            maxLength={160}
            onChange={(value) => updateCredential("username", value.trim())}
          />
          <PasswordField
            label="密码"
            value={credentials.password}
            autoComplete="new-password"
            onChange={(value) => updateCredential("password", value)}
          />
          <PasswordField
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
              className="btn btn-secondary btn-sm"
              disabled={connectionApi.loading || validationError !== null}
            >
              {connectionApi.loading ? "测试中..." : "测试 BRAIN 连接"}
            </button>
            <p className={`text-xs ${connectionApi.error ? "text-negative" : connectionApi.data?.ok ? "text-positive" : "text-text-tertiary"}`} role="status" aria-live="polite">
              {connectionStatusText}
            </p>
          </div>
        </ConfigSection>
      )}

      <ConfigSection title="BRAIN 设置" description="字段和选项来自后端公开的官方能力集校验，不在前端自定义扩展。">
        <details open className="col-span-full group/config-details mb-2">
          <summary className="text-sm font-medium text-text-secondary cursor-pointer py-1 select-none hover:text-text-primary transition-colors">基础参数</summary>
          <div className="mt-3 grid grid-cols-1 gap-x-5 gap-y-4 md:grid-cols-2">
            <SelectField label="资产类型" value={form.instrumentType} options={optionValues(options, "instrumentType", form.instrumentType, DEFAULT_INSTRUMENT_TYPE_OPTIONS)} onChange={(value) => update("instrumentType", value)} />
            <SelectField label="区域" value={form.region} options={optionValues(options, "region", form.region, DEFAULT_REGION_OPTIONS)} help={helpContent("region")} onChange={(value) => update("region", value)} />
            <SelectField label="股票池" value={form.universe} options={optionValues(options, "universe", form.universe, DEFAULT_UNIVERSE_OPTIONS)} help={helpContent("universe")} onChange={(value) => update("universe", value)} />
            <SelectField label="延迟" value={String(form.delay)} options={optionValues(options, "delay", String(form.delay), DEFAULT_DELAY_OPTIONS)} help={helpContent("delay")} onChange={(value) => update("delay", Number(value))} />
            <NumberField label="衰减" value={form.decay} min={0} step={1} help={helpContent("decay")} onChange={(value) => update("decay", value)} />
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
          </div>
        </details>
        <details className="col-span-full group/config-details mb-2">
          <summary className="text-sm font-medium text-text-secondary cursor-pointer py-1 select-none hover:text-text-primary transition-colors">高级参数</summary>
          <div className="mt-3 grid grid-cols-1 gap-x-5 gap-y-4 md:grid-cols-2">
            <SelectField label="中性化" value={form.neutralization} options={optionValues(options, "neutralization", form.neutralization, DEFAULT_NEUTRALIZATION_OPTIONS)} help={helpContent("neutralization")} onChange={(value) => update("neutralization", value)} />
            <SelectField label="数据净化" value={form.pasteurization} options={optionValues(options, "pasteurization", form.pasteurization, DEFAULT_PASTEURIZATION_OPTIONS)} help={helpContent("pasteurization")} onChange={(value) => update("pasteurization", value)} />
            <SelectField label="单位处理" value={form.unitHandling} options={optionValues(options, "unitHandling", form.unitHandling, DEFAULT_UNIT_HANDLING_OPTIONS)} help={helpContent("unitHandling")} onChange={(value) => update("unitHandling", value)} />
            <SelectField label="空值处理" value={form.nanHandling} options={optionValues(options, "nanHandling", form.nanHandling, DEFAULT_NAN_HANDLING_OPTIONS)} help={helpContent("nanHandling")} onChange={(value) => update("nanHandling", value)} />
            <SelectField label="语言" value={form.language} options={optionValues(options, "language", form.language, DEFAULT_LANGUAGE_OPTIONS)} onChange={(value) => update("language", value)} />
          </div>
        </details>
      </ConfigSection>

      <ConfigSection title="预算控制" description="用于限制单次生产运行的候选数量、轮次和回测批量。">
        <NumberField label="每轮最大候选数" value={form.candidates} min={1} max={1000} step={1} onChange={(value) => update("candidates", value)} />
        <NumberField label="最大轮次" value={form.cycles} min={1} max={10000} step={1} onChange={(value) => update("cycles", value)} />
        <NumberField label="候选池大小" value={form.poolSize} min={1} max={5000} step={1} onChange={(value) => update("poolSize", value)} />
        <NumberField label="回测批处理大小" value={form.backtestBatchSize} min={1} max={100} step={1} onChange={(value) => update("backtestBatchSize", value)} />
        <div>
          <CheckboxField label="每次运行前强制云端同步" checked={form.requireCloudSync} onChange={(value) => update("requireCloudSync", value)} />
          <p className="mt-1 text-xs leading-5 text-text-tertiary">
            默认关闭：首次无缓存时自动同步，之后直接使用本地缓存；开启后，每次生产运行前都会重新拉取云端 Alpha 与官方能力集。
          </p>
        </div>
      </ConfigSection>

      <ConfigSection title="质量阈值" description="提交前门禁，低于阈值的候选只能进入研究或优化状态。">
        <NumberField label="最低夏普比率" value={form.minSharpe} min={0} step={0.01} help={helpContent("minSharpe")} onChange={(value) => update("minSharpe", value)} />
        <NumberField label="最低适应度" value={form.minFitness} min={0} step={0.01} help={helpContent("minFitness")} onChange={(value) => update("minFitness", value)} />
        <NumberField label="最低换手率" value={form.minTurnover} min={0} max={1} step={0.01} onChange={(value) => update("minTurnover", value)} />
        <NumberField label="最高换手率" value={form.platformMaxTurnover} min={0} max={1} step={0.01} onChange={(value) => update("platformMaxTurnover", value)} />
        <NumberField label="最大自相关性" value={form.maxSelfCorrelation} min={0} max={1} step={0.01} help={helpContent("maxSelfCorrelation")} onChange={(value) => update("maxSelfCorrelation", value)} />
        <NumberField label="最大权重集中度" value={form.maxWeightConcentration} min={0} max={1} step={0.01} onChange={(value) => update("maxWeightConcentration", value)} />
      </ConfigSection>

      <ConfigSection title="评分配置" description="当前评分层权重为只读展示，避免和官方门禁配置混淆。">
        <ConfigValue label="先验权重" value={scoring?.prior_layer_weight} />
        <ConfigValue label="经验权重" value={scoring?.empirical_layer_weight} />
        <ConfigValue label="检查清单权重" value={scoring?.checklist_layer_weight} />
        <ConfigValue label="市场状态" value={scoring?.market_regime} />
        {/* P2-4: 查看详细权重按钮 */}
        <div className="col-span-full mt-2">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => setShowWeightModal(true)}
          >
            查看详细权重
          </button>
        </div>
      </ConfigSection>

      <ConfigSection title="环境设置" description="本地 Web 页面只允许保存非提交运行配置；真实提交必须走单独的人工确认流程。">
        <ConfigValue label="自动提交" value="关闭（Web 保存强制）" />
      </ConfigSection>

      {/* P2-4: 评分权重透明化 Modal */}
      {showWeightModal && (
        <ScoringWeightModal
          schema={schema}
          scoring={scoring}
          onClose={() => setShowWeightModal(false)}
        />
      )}
    </form>
  );
}

